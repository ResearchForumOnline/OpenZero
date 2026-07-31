const express = require('express');
const puppeteer = require('puppeteer');
const crypto = require('crypto');

const app = express();
app.use(express.json({ limit: '1mb' }));

let browser;
let page;
let lastNavigation = null;
let lastError = null;
let snapshotId = '';
let ownerRunId = '';
let ownerGeneration = 0;
let elementRegistry = new Map();
let descriptorRegistry = new Map();

function normalizeUrl(url) {
    if (!url) return '';
    const value = String(url).trim();
    if (!value) return '';
    return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function cleanText(value, maxLength = 240) {
    return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

const RUN_ID_RE = /^[a-f0-9]{32}$/i;

function runOwnershipError(message, statusCode) {
    const error = new Error(message);
    error.statusCode = statusCode;
    return error;
}

function requestRunId(req) {
    const bodyRunId = String((req.body && req.body.run_id) || '').trim().toLowerCase();
    const queryRunId = String((req.query && req.query.run_id) || '').trim().toLowerCase();
    if (bodyRunId && queryRunId && bodyRunId !== queryRunId) {
        throw runOwnershipError('Conflicting Moltbot run_id values.', 400);
    }
    const runId = bodyRunId || queryRunId;
    if (!RUN_ID_RE.test(runId)) {
        throw runOwnershipError('A valid 32-character hexadecimal run_id is required.', 400);
    }
    return runId;
}

function claimBrowserOwner(runId) {
    if (ownerRunId && ownerRunId !== runId) {
        throw runOwnershipError('Moltbot is owned by another autonomous run.', 409);
    }
    if (!ownerRunId) {
        ownerRunId = runId;
        ownerGeneration += 1;
    }
}

function requireBrowserOwner(req) {
    const runId = requestRunId(req);
    if (!ownerRunId) {
        throw runOwnershipError('Moltbot has no active owner; claim it through /goto first.', 409);
    }
    if (ownerRunId !== runId) {
        throw runOwnershipError('Moltbot is owned by another autonomous run.', 409);
    }
    return runId;
}

function routeErrorStatus(error, fallbackStatus) {
    const statusCode = Number(error && error.statusCode);
    return Number.isInteger(statusCode) && statusCode >= 400 && statusCode <= 599
        ? statusCode
        : fallbackStatus;
}

function detachElementRegistry() {
    const handles = Array.from(elementRegistry.values());
    elementRegistry = new Map();
    descriptorRegistry = new Map();
    snapshotId = '';
    return handles;
}

async function disposeElementHandles(handles) {
    await Promise.all(handles.map((handle) => handle.dispose().catch(() => {})));
}

async function clearElementRegistry() {
    await disposeElementHandles(detachElementRegistry());
}

function detachBrowserOwner(req) {
    const runId = requireBrowserOwner(req);
    const releasedGeneration = ownerGeneration;
    // Detach the owner and its snapshot synchronously, before yielding to any
    // handle disposal. A duplicate release therefore cannot resume later and
    // clear a newer owner's state.
    const handles = detachElementRegistry();
    ownerRunId = '';
    ownerGeneration += 1;
    return {
        run_id: runId,
        released_generation: releasedGeneration,
        handles
    };
}

function classifyElement(descriptor, currentUrl) {
    const label = cleanText(
        `${descriptor.label || ''} ${descriptor.text || ''} ${descriptor.name || ''}`,
        500
    );
    const type = String(descriptor.type || '').toLowerCase();
    const tag = String(descriptor.tag || '').toLowerCase();
    const isSubmitControl =
        Boolean(descriptor.form_associated) &&
        (
            (tag === 'input' && ['submit', 'image'].includes(type)) ||
            (tag === 'button' && type === 'submit')
        );
    const sensitive =
        /\b(?:password|passcode|payment|card|cvv|cvc|secret|token|otp|one[\s-]?time|captcha)\b/i;
    const personal =
        /\b(?:address|email|e-mail|full name|first name|last name|phone|telephone|postcode|zip code)\b/i;
    const consequential =
        /\b(?:apply|authorize|book|buy|cancel|checkout|confirm|delete|grant|install|log\s*in|order|pay|post|publish|purchase|remove|reserve|send|sign\s*(?:in|up)|submit|subscribe|transfer|upload)\b/i;
    if (type === 'password' || type === 'file' || sensitive.test(label)) {
        return {
            risk: 'blocked_sensitive',
            sensitive_kind: type === 'file' ? 'file_upload' : 'secret'
        };
    }
    if (descriptor.href) {
        try {
            if (new URL(descriptor.href).origin !== new URL(currentUrl).origin) {
                return { risk: 'cross_origin', sensitive_kind: '' };
            }
        } catch (_) {
            return { risk: 'blocked_sensitive', sensitive_kind: 'invalid_url' };
        }
    }
    if (consequential.test(label) || type === 'submit' || isSubmitControl) {
        return { risk: 'consequential', sensitive_kind: '' };
    }
    if (personal.test(label) || ['email', 'tel'].includes(type)) {
        return { risk: 'personal_data', sensitive_kind: '' };
    }
    return { risk: 'normal', sensitive_kind: '' };
}

async function launchBrowser() {
    console.log('>>> LAUNCHING HEADLESS CHROME...');
    try {
        browser = await puppeteer.launch({
            headless: 'new',
            executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome-stable',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-dev-shm-usage',
                '--single-process'
            ]
        });
        page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 900, deviceScaleFactor: 1 });
        await page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
            '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        );
        console.log('>>> BROWSER IS OPEN AND READY.');
        lastError = null;
    } catch (error) {
        console.error('!!! FAILED TO LAUNCH BROWSER !!!');
        console.error(error);
        lastError = error.message || String(error);
    }
}

async function ensurePage() {
    if (!browser || !browser.isConnected()) {
        await launchBrowser();
    }
    if (!browser) {
        throw new Error('Browser not initialized yet.');
    }
    if (!page || page.isClosed()) {
        page = await browser.newPage();
        await page.setViewport({ width: 1366, height: 900, deviceScaleFactor: 1 });
    }
    return page;
}

async function captureScreenshot(filename = 'vision.png', fullPage = false) {
    const activePage = await ensurePage();
    const safeName = String(filename || 'vision.png').replace(/[^A-Za-z0-9_.-]/g, '_');
    const path = `../static/${safeName}`;
    await activePage.screenshot({ path, fullPage: Boolean(fullPage) });
    return `static/${safeName}`;
}

async function pageText(maxChars = 8000) {
    const activePage = await ensurePage();
    const text = await activePage.evaluate(() => (document.body ? document.body.innerText : ''));
    return String(text || 'NO TEXT')
        .replace(/\s+/g, ' ')
        .trim()
        .substring(0, Math.max(500, Math.min(Number(maxChars) || 8000, 30000)));
}

async function pageStateDigest(activePage) {
    const targetPage = activePage || await ensurePage();
    return targetPage.evaluate(() => {
        const compact = (value, maxLength) =>
            String(value || '')
                .replace(/\s+/g, ' ')
                .trim()
                .slice(0, maxLength);
        const visible = (element) => {
            if (!(element instanceof Element) || !element.isConnected) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                Number.parseFloat(style.opacity || '1') >= 0.02 &&
                rect.width >= 1 &&
                rect.height >= 1
            );
        };
        const selector =
            'a[href],button,input,textarea,select,[role="button"],[role="link"],[tabindex]';
        const interactive = Array.from(document.querySelectorAll(selector))
            .filter(visible)
            .slice(0, 120)
            .map((element, index) => ({
                index,
                tag: compact(element.tagName, 24).toLowerCase(),
                role: compact(element.getAttribute('role'), 32),
                type: compact(element.type || element.getAttribute('type'), 32).toLowerCase(),
                disabled: Boolean(
                    element.disabled || element.getAttribute('aria-disabled') === 'true'
                ),
                checked:
                    typeof element.checked === 'boolean' &&
                    ['checkbox', 'radio'].includes(String(element.type || '').toLowerCase())
                        ? element.checked
                        : null,
                selected_index:
                    element instanceof HTMLSelectElement ? element.selectedIndex : null,
                aria_checked: compact(element.getAttribute('aria-checked'), 32),
                aria_selected: compact(element.getAttribute('aria-selected'), 32),
                aria_expanded: compact(element.getAttribute('aria-expanded'), 32),
                aria_pressed: compact(element.getAttribute('aria-pressed'), 32),
                aria_disabled: compact(element.getAttribute('aria-disabled'), 32),
                aria_hidden: compact(element.getAttribute('aria-hidden'), 32),
                aria_current: compact(element.getAttribute('aria-current'), 32),
                aria_invalid: compact(element.getAttribute('aria-invalid'), 32),
                aria_busy: compact(element.getAttribute('aria-busy'), 32)
            }));
        return {
            url: location.href,
            title: compact(document.title, 500),
            visible_text: compact(document.body ? document.body.innerText : '', 8000),
            interactive
        };
    });
}

function pageStateHash(digest) {
    return crypto
        .createHash('sha256')
        .update(JSON.stringify(digest), 'utf8')
        .digest('hex');
}

async function safeFieldValueLength(handle) {
    try {
        return await handle.evaluate((element) => {
            if (!['INPUT', 'TEXTAREA'].includes(String(element.tagName || '').toUpperCase())) {
                return null;
            }
            const current = Reflect.get(element, 'value');
            return typeof current === 'string' ? current.length : null;
        });
    } catch (_) {
        return null;
    }
}

async function captureFieldValueState(handle) {
    try {
        // Return an object handle, not the value. CDP keeps the field value in
        // the page realm and only the later boolean comparison crosses out.
        return await handle.evaluateHandle((element) => {
            const current = Reflect.get(element, 'value');
            return {
                eligible:
                    ['INPUT', 'TEXTAREA'].includes(
                        String(element.tagName || '').toUpperCase()
                    ) && typeof current === 'string',
                value: typeof current === 'string' ? current : null
            };
        });
    } catch (_) {
        return null;
    }
}

async function safeFieldValueChanged(handle, beforeStateHandle) {
    if (!beforeStateHandle) return false;
    try {
        return Boolean(
            await handle.evaluate((element, beforeState) => {
                if (!beforeState || beforeState.eligible !== true) return false;
                const current = Reflect.get(element, 'value');
                return (
                    typeof current === 'string' &&
                    typeof beforeState.value === 'string' &&
                    current !== beforeState.value
                );
            }, beforeStateHandle)
        );
    } catch (_) {
        return false;
    }
}

function inputSha256(text) {
    return crypto
        .createHash('sha256')
        .update(String(text || ''), 'utf8')
        .digest('hex');
}

async function targetStateDigest(handle) {
    try {
        return await handle.evaluate((element) => {
            if (!(element instanceof Element) || !element.isConnected) {
                return { connected: false };
            }
            const compact = (value, maxLength) =>
                String(value || '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .slice(0, maxLength);
            const type = compact(element.type || element.getAttribute('type'), 32).toLowerCase();
            const classTokens = Array.from(element.classList || [])
                .map((token) => compact(token, 80))
                .filter(Boolean)
                .sort()
                .slice(0, 24);
            return {
                connected: true,
                class_name: classTokens.join(' '),
                disabled: Boolean(
                    element.disabled || element.getAttribute('aria-disabled') === 'true'
                ),
                checked:
                    typeof element.checked === 'boolean' &&
                    ['checkbox', 'radio'].includes(type)
                        ? element.checked
                        : null,
                selected_index:
                    element instanceof HTMLSelectElement ? element.selectedIndex : null,
                aria_checked: compact(element.getAttribute('aria-checked'), 32),
                aria_selected: compact(element.getAttribute('aria-selected'), 32),
                aria_expanded: compact(element.getAttribute('aria-expanded'), 32),
                aria_pressed: compact(element.getAttribute('aria-pressed'), 32),
                aria_disabled: compact(element.getAttribute('aria-disabled'), 32),
                aria_hidden: compact(element.getAttribute('aria-hidden'), 32),
                aria_current: compact(element.getAttribute('aria-current'), 32),
                aria_invalid: compact(element.getAttribute('aria-invalid'), 32),
                aria_busy: compact(element.getAttribute('aria-busy'), 32)
            };
        });
    } catch (_) {
        return { connected: false };
    }
}

async function startTrustedClickObservation(handle) {
    try {
        return await handle.evaluateHandle((element) => {
            const state = { observed: false };
            const listener = (event) => {
                if (
                    event.isTrusted === true &&
                    (event.target === element || element.contains(event.target))
                ) {
                    state.observed = true;
                }
            };
            element.addEventListener('click', listener, true);
            state.stop = () => element.removeEventListener('click', listener, true);
            return state;
        });
    } catch (_) {
        return null;
    }
}

async function finishTrustedClickObservation(trackerHandle) {
    if (!trackerHandle) return false;
    try {
        return Boolean(
            await trackerHandle.evaluate((state) => {
                if (state && typeof state.stop === 'function') {
                    state.stop();
                }
                return Boolean(state && state.observed === true);
            })
        );
    } catch (_) {
        return false;
    } finally {
        await trackerHandle.dispose().catch(() => {});
    }
}

function watchNavigation(activePage) {
    let observed = false;
    const promise = activePage
        .waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 5000 })
        .then(() => {
            observed = true;
            return true;
        })
        .catch(() => false);
    return {
        promise,
        wasObserved: () => observed
    };
}

async function settledPageProof(activePage, beforeHash, settleMs = 250) {
    const initialAfterHash = pageStateHash(await pageStateDigest(activePage));
    await sleep(settleMs);
    const afterHash = pageStateHash(await pageStateDigest(activePage));
    return {
        initial_after_hash: initialAfterHash,
        after_hash: afterHash,
        stable_page_change:
            beforeHash !== initialAfterHash && initialAfterHash === afterHash
    };
}

async function ambiguousActionError(res, metadata = {}) {
    // Invalidate the action snapshot before yielding. The caller must never
    // replay an action whose dispatch may already have reached the page.
    const handles = detachElementRegistry();
    await disposeElementHandles(handles);
    const signals = {
        ...(metadata.verification_signals || {}),
        proof_error: true
    };
    return res.status(409).json({
        status: 'error',
        content:
            'The browser action was dispatched, but its outcome could not be verified. ' +
            'Do not retry automatically; inspect the page again.',
        dispatched: true,
        outcome_ambiguous: true,
        retry_safe: false,
        requires_reinspection: true,
        acted_element: metadata.acted_element || {},
        before_hash: metadata.before_hash || '',
        initial_after_hash: metadata.initial_after_hash || '',
        after_hash: metadata.after_hash || '',
        verification_signals: signals,
        state_changed: false,
        ...(Number.isInteger(metadata.input_length)
            ? {
                input_length: metadata.input_length,
                input_sha256: metadata.input_sha256 || ''
            }
            : {})
    });
}

async function pageLinks(maxLinks = 80) {
    const activePage = await ensurePage();
    const links = await activePage.evaluate(() =>
        Array.from(document.querySelectorAll('a[href]')).map((link) => ({
            text: (link.innerText || link.getAttribute('aria-label') || '')
                .trim()
                .replace(/\s+/g, ' '),
            href: link.href
        }))
    );
    return links
        .filter((link) => link.href)
        .slice(0, Math.max(1, Math.min(Number(maxLinks) || 80, 200)));
}

async function inspectPage(maxElements = 80, maxChars = 8000) {
    const activePage = await ensurePage();
    await clearElementRegistry();
    snapshotId = crypto.randomUUID();
    const handles = await activePage.$$(
        'a[href],button,input,textarea,select,[role="button"],[role="link"],[tabindex]'
    );
    const interactive = [];
    const boundedHandles = handles.slice(
        0,
        Math.max(1, Math.min(Number(maxElements) || 80, 120))
    );
    for (const handle of boundedHandles) {
        let descriptor;
        try {
            descriptor = await handle.evaluate((element) => {
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                if (
                    style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    rect.width < 1 ||
                    rect.height < 1
                ) {
                    return null;
                }
                const label =
                    element.getAttribute('aria-label') ||
                    element.labels?.[0]?.innerText ||
                    element.getAttribute('title') ||
                    element.getAttribute('placeholder') ||
                    '';
                return {
                    tag: String(element.tagName || '').toLowerCase(),
                    role: element.getAttribute('role') || '',
                    type: String(element.type || element.getAttribute('type') || ''),
                    name: element.getAttribute('name') || '',
                    form_associated: Boolean(element.form),
                    label,
                    // Never disclose form values in an inspection. Password,
                    // personal, and other typed values stay inside the page.
                    text: element.innerText || '',
                    href: element.href || '',
                    disabled: Boolean(
                        element.disabled || element.getAttribute('aria-disabled') === 'true'
                    )
                };
            });
        } catch (_) {
            descriptor = null;
        }
        if (!descriptor) {
            await handle.dispose().catch(() => {});
            continue;
        }
        const elementId = `e${interactive.length + 1}`;
        const classification = classifyElement(descriptor, activePage.url());
        const publicDescriptor = publicPolicyDescriptor({
            ...descriptor,
            risk: classification.risk,
            sensitive_kind: classification.sensitive_kind
        }, elementId);
        elementRegistry.set(elementId, handle);
        descriptorRegistry.set(elementId, publicDescriptor);
        interactive.push(publicDescriptor);
    }
    // Puppeteer returns every match, but only a bounded visible subset belongs
    // to this ephemeral snapshot. Dispose the rest to avoid handle leaks.
    await Promise.all(
        handles.slice(boundedHandles.length).map((handle) => handle.dispose().catch(() => {}))
    );
    return {
        snapshot_id: snapshotId,
        url: activePage.url(),
        title: await activePage.title(),
        content: await pageText(maxChars),
        interactive
    };
}

function requireInspectedElement(body) {
    const suppliedSnapshot = String((body && body.snapshot_id) || '');
    const elementId = String((body && body.element_id) || '');
    if (!snapshotId || suppliedSnapshot !== snapshotId) {
        throw new Error('Page snapshot is stale; inspect the page again.');
    }
    const handle = elementRegistry.get(elementId);
    const descriptor = descriptorRegistry.get(elementId);
    if (!handle || !descriptor) {
        throw new Error('The requested element_id is not in the latest inspected snapshot.');
    }
    if (descriptor.disabled) {
        throw new Error('The inspected element is disabled.');
    }
    if (descriptor.risk === 'blocked_sensitive') {
        throw new Error(`Moltbot blocks ${descriptor.sensitive_kind || 'sensitive'} elements.`);
    }
    return { handle, descriptor };
}

const MATERIAL_DESCRIPTOR_FIELDS = Object.freeze([
    'tag',
    'role',
    'type',
    'name',
    'form_associated',
    'label',
    'text',
    'href',
    'disabled',
    'risk',
    'sensitive_kind'
]);

function publicPolicyDescriptor(descriptor, elementId = '') {
    return {
        ...(elementId ? { id: cleanText(elementId, 80) } : {}),
        tag: cleanText(descriptor.tag, 24).toLowerCase(),
        role: cleanText(descriptor.role, 32),
        type: cleanText(descriptor.type, 32).toLowerCase(),
        name: cleanText(descriptor.name, 120),
        form_associated: Boolean(descriptor.form_associated),
        label: cleanText(descriptor.label, 160),
        text: cleanText(descriptor.text, 180),
        href: cleanText(descriptor.href, 500),
        disabled: Boolean(descriptor.disabled),
        risk: cleanText(descriptor.risk, 32),
        sensitive_kind: cleanText(descriptor.sensitive_kind, 32)
    };
}

function requireStableDescriptor(inspectedDescriptor, liveDescriptor) {
    const inspected = publicPolicyDescriptor(inspectedDescriptor);
    const live = publicPolicyDescriptor(liveDescriptor);
    const changed = MATERIAL_DESCRIPTOR_FIELDS.some(
        (field) => inspected[field] !== live[field]
    );
    if (changed) {
        throw new Error(
            'The inspected element changed materially; inspect the page again before acting.'
        );
    }
    return live;
}

async function livePolicyDescriptor(handle, currentUrl) {
    const descriptor = await handle.evaluate((element) => {
        const label =
            element.getAttribute('aria-label') ||
            element.labels?.[0]?.innerText ||
            element.getAttribute('title') ||
            element.getAttribute('placeholder') ||
            '';
        return {
            connected: Boolean(element.isConnected),
            tag: String(element.tagName || '').toLowerCase(),
            role: element.getAttribute('role') || '',
            type: String(element.type || element.getAttribute('type') || ''),
            name: element.getAttribute('name') || '',
            form_associated: Boolean(element.form),
            label,
            text: element.innerText || '',
            href: element.href || '',
            disabled: Boolean(
                element.disabled || element.getAttribute('aria-disabled') === 'true'
            )
        };
    });
    if (!descriptor.connected) {
        throw new Error('The inspected element is disconnected; inspect the page again.');
    }
    const classification = classifyElement(descriptor, currentUrl);
    return {
        ...descriptor,
        risk: classification.risk,
        sensitive_kind: classification.sensitive_kind
    };
}

function enforceLiveElementPolicy(descriptor, confirmed, actionLabel) {
    if (descriptor.disabled) {
        throw new Error('The inspected element became disabled.');
    }
    if (descriptor.risk === 'blocked_sensitive') {
        throw new Error(`Moltbot blocks ${descriptor.sensitive_kind || 'sensitive'} elements.`);
    }
    if (
        ['consequential', 'cross_origin', 'personal_data'].includes(descriptor.risk) &&
        !confirmed
    ) {
        throw new Error(`This inspected browser ${actionLabel} requires fresh confirmation.`);
    }
}

launchBrowser();

app.get('/status', async (_req, res) => {
    const connected = Boolean(browser && browser.isConnected && browser.isConnected());
    res.json({
        status: connected ? 'ready' : 'error',
        browser_connected: connected,
        page_open: Boolean(page && !page.isClosed()),
        current_url: page && !page.isClosed() ? page.url() : '',
        snapshot_id: snapshotId,
        owner_run_id: ownerRunId,
        owner_generation: ownerGeneration,
        last_navigation: lastNavigation,
        last_error: lastError
    });
});

app.post('/release', async (req, res) => {
    try {
        const release = detachBrowserOwner(req);
        await disposeElementHandles(release.handles);
        res.json({
            status: 'success',
            released: true,
            released_owner_run_id: release.run_id,
            released_generation: release.released_generation,
            owner_generation: ownerGeneration,
            owner_reassigned: Boolean(ownerRunId)
        });
    } catch (error) {
        lastError = error.message || String(error);
        res.status(routeErrorStatus(error, 500)).json({ status: 'error', content: lastError });
    }
});

app.post('/goto', async (req, res) => {
    try {
        const runId = requestRunId(req);
        const url = normalizeUrl(req.body && req.body.url);
        if (!url) {
            throw runOwnershipError('Missing URL.', 400);
        }
        claimBrowserOwner(runId);
        const activePage = await ensurePage();
        console.log('NAVIGATING TO:', url);
        await activePage.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
        lastNavigation = { url, at: new Date().toISOString() };
        lastError = null;
        let screenshot = '';
        try {
            screenshot = await captureScreenshot('vision.png', false);
        } catch (error) {
            console.log(`Screenshot failed (non-fatal): ${error.message}`);
        }
        res.json({
            status: 'success',
            ...(await inspectPage(req.body.max_elements || 80, req.body.max_chars || 8000)),
            links: await pageLinks(req.body.max_links || 40),
            screenshot
        });
    } catch (error) {
        console.error('ERROR navigating:', error.message);
        lastError = error.message || String(error);
        res.status(routeErrorStatus(error, 500)).json({ status: 'error', content: lastError });
    }
});

app.get('/text', async (req, res) => {
    try {
        res.json({
            status: 'success',
            url: page ? page.url() : '',
            content: await pageText(req.query.max_chars || 8000)
        });
    } catch (error) {
        lastError = error.message || String(error);
        res.status(500).json({ status: 'error', content: lastError });
    }
});

app.post('/inspect', async (req, res) => {
    try {
        requireBrowserOwner(req);
        res.json({
            status: 'success',
            ...(await inspectPage(
                req.body && req.body.max_elements,
                req.body && req.body.max_chars
            ))
        });
    } catch (error) {
        lastError = error.message || String(error);
        res.status(routeErrorStatus(error, 500)).json({ status: 'error', content: lastError });
    }
});

app.get('/element/:elementId', async (req, res) => {
    try {
        requireBrowserOwner(req);
        const descriptor = descriptorRegistry.get(String(req.params.elementId || ''));
        const valid = snapshotId && String(req.query.snapshot_id || '') === snapshotId;
        return valid && descriptor
            ? res.json({ status: 'success', snapshot_id: snapshotId, element: descriptor })
            : res
                .status(409)
                .json({ status: 'error', content: 'Element snapshot is stale or unknown.' });
    } catch (error) {
        lastError = error.message || String(error);
        return res
            .status(routeErrorStatus(error, 409))
            .json({ status: 'error', content: lastError });
    }
});

app.get('/links', async (req, res) => {
    try {
        res.json({
            status: 'success',
            url: page ? page.url() : '',
            links: await pageLinks(req.query.max_links || 80)
        });
    } catch (error) {
        lastError = error.message || String(error);
        res.status(500).json({ status: 'error', content: lastError });
    }
});

app.post('/screenshot', async (req, res) => {
    try {
        const screenshot = await captureScreenshot(
            req.body && req.body.filename,
            Boolean(req.body && req.body.full_page)
        );
        res.json({ status: 'success', screenshot });
    } catch (error) {
        lastError = error.message || String(error);
        res.status(500).json({ status: 'error', content: lastError });
    }
});

app.post('/click', async (req, res) => {
    let dispatched = false;
    let clickTracker = null;
    let actedElement = {};
    let beforeHash = '';
    let verificationSignals = {};
    try {
        requireBrowserOwner(req);
        const activePage = await ensurePage();
        const { handle, descriptor } = requireInspectedElement(req.body);
        const liveDescriptor = await livePolicyDescriptor(handle, activePage.url());
        const stableDescriptor = requireStableDescriptor(descriptor, liveDescriptor);
        actedElement = { id: descriptor.id, ...stableDescriptor };
        enforceLiveElementPolicy(
            actedElement,
            Boolean(req.body && req.body.confirmed),
            'action'
        );
        const beforeUrl = activePage.url();
        beforeHash = pageStateHash(await pageStateDigest(activePage));
        const beforeTargetState = await targetStateDigest(handle);
        if (!beforeTargetState.connected) {
            throw new Error('The inspected element is disconnected; inspect the page again.');
        }
        const beforeTargetHash = pageStateHash(beforeTargetState);
        clickTracker = await startTrustedClickObservation(handle);
        const navigation = watchNavigation(activePage);
        dispatched = true;
        await handle.click();
        await Promise.race([navigation.promise, sleep(700)]);
        const pageProof = await settledPageProof(activePage, beforeHash);
        const afterTargetState = await targetStateDigest(handle);
        const afterTargetHash = pageStateHash(afterTargetState);
        const afterUrl = activePage.url();
        const targetDisconnected =
            beforeTargetState.connected && !afterTargetState.connected;
        const targetStateChanged =
            beforeTargetState.connected &&
            afterTargetState.connected &&
            beforeTargetHash !== afterTargetHash;
        const trustedTargetClick = await finishTrustedClickObservation(clickTracker);
        clickTracker = null;
        const targetScopedPageChange =
            trustedTargetClick && pageProof.stable_page_change;
        verificationSignals = {
            navigation_observed: navigation.wasObserved(),
            url_changed: beforeUrl !== afterUrl,
            target_disconnected: targetDisconnected,
            target_state_changed: targetStateChanged,
            trusted_target_click: trustedTargetClick,
            stable_page_change: pageProof.stable_page_change,
            click_event_page_change: targetScopedPageChange
        };
        const stateChanged = Boolean(
            verificationSignals.navigation_observed ||
            verificationSignals.url_changed ||
            targetDisconnected ||
            targetStateChanged ||
            targetScopedPageChange
        );
        const next = await inspectPage(80, 5000);
        res.json({
            status: 'success',
            action: `Clicked ${actedElement.label || actedElement.text || descriptor.id}.`,
            dispatched: true,
            outcome_ambiguous: !stateChanged,
            retry_safe: false,
            requires_reinspection: !stateChanged,
            acted_element: actedElement,
            before_hash: beforeHash,
            initial_after_hash: pageProof.initial_after_hash,
            after_hash: pageProof.after_hash,
            verification_signals: verificationSignals,
            state_changed: stateChanged,
            ...next
        });
    } catch (error) {
        if (clickTracker) {
            await finishTrustedClickObservation(clickTracker);
            clickTracker = null;
        }
        lastError = error.message || String(error);
        if (dispatched) {
            return ambiguousActionError(res, {
                acted_element: actedElement,
                before_hash: beforeHash,
                verification_signals: verificationSignals
            });
        }
        return res.status(routeErrorStatus(error, 409)).json({
            status: 'error',
            content: lastError,
            dispatched: false,
            outcome_ambiguous: false,
            retry_safe: false,
            requires_reinspection: true,
            acted_element: actedElement,
            before_hash: beforeHash,
            initial_after_hash: '',
            after_hash: '',
            verification_signals: verificationSignals,
            state_changed: false
        });
    }
});

app.post('/type', async (req, res) => {
    let dispatched = false;
    let actedElement = {};
    let beforeHash = '';
    let beforeValueState = null;
    let verificationSignals = {};
    let inputLength = 0;
    let inputDigest = '';
    try {
        requireBrowserOwner(req);
        const text = String((req.body && req.body.text) || '');
        inputLength = [...text].length;
        inputDigest = inputSha256(text);
        if (text.length > 4000) {
            return res.status(400).json({
                status: 'error',
                content: 'Text is limited to 4,000 characters.',
                dispatched: false,
                outcome_ambiguous: false,
                retry_safe: true,
                requires_reinspection: false,
                acted_element: {},
                before_hash: '',
                initial_after_hash: '',
                after_hash: '',
                verification_signals: {},
                state_changed: false,
                input_length: inputLength,
                input_sha256: inputDigest
            });
        }
        const activePage = await ensurePage();
        const { handle, descriptor } = requireInspectedElement(req.body);
        const liveDescriptor = await livePolicyDescriptor(handle, activePage.url());
        const stableDescriptor = requireStableDescriptor(descriptor, liveDescriptor);
        actedElement = { id: descriptor.id, ...stableDescriptor };
        if (!['input', 'textarea'].includes(actedElement.tag)) {
            throw new Error('The inspected element is not a text field.');
        }
        enforceLiveElementPolicy(
            actedElement,
            Boolean(req.body && req.body.confirmed),
            'entry'
        );
        // Focusing is itself a browser interaction and may run page handlers.
        // Treat the attempt as dispatch-risk so any later failure is ambiguous,
        // while taking all proof baselines only after focus succeeds.
        dispatched = true;
        await handle.focus();
        const beforeUrl = activePage.url();
        beforeHash = pageStateHash(await pageStateDigest(activePage));
        // Capture every accepted causal baseline after focus so an onfocus
        // URL, class, ARIA, or value change cannot prove that typing succeeded.
        const beforeTargetState = await targetStateDigest(handle);
        if (!beforeTargetState.connected) {
            throw new Error('The inspected element is disconnected; inspect the page again.');
        }
        const beforeTargetHash = pageStateHash(beforeTargetState);
        beforeValueState = await captureFieldValueState(handle);
        const beforeValueLength = await safeFieldValueLength(handle);
        const navigation = watchNavigation(activePage);
        if (req.body && req.body.clear) {
            await activePage.keyboard.down('Control');
            await activePage.keyboard.press('A');
            await activePage.keyboard.up('Control');
        }
        await activePage.keyboard.type(text, { delay: 10 });
        await Promise.race([navigation.promise, sleep(250)]);
        const valueChanged = await safeFieldValueChanged(handle, beforeValueState);
        if (beforeValueState) {
            await beforeValueState.dispose().catch(() => {});
            beforeValueState = null;
        }
        const afterValueLength = await safeFieldValueLength(handle);
        const valueLengthChanged =
            Number.isInteger(beforeValueLength) &&
            Number.isInteger(afterValueLength) &&
            beforeValueLength !== afterValueLength;
        const pageProof = await settledPageProof(activePage, beforeHash);
        const afterTargetState = await targetStateDigest(handle);
        const afterTargetHash = pageStateHash(afterTargetState);
        const afterUrl = activePage.url();
        const targetDisconnected =
            beforeTargetState.connected && !afterTargetState.connected;
        const targetStateChanged =
            beforeTargetState.connected &&
            afterTargetState.connected &&
            beforeTargetHash !== afterTargetHash;
        verificationSignals = {
            value_changed: valueChanged,
            value_length_changed: valueLengthChanged,
            navigation_observed: navigation.wasObserved(),
            url_changed: beforeUrl !== afterUrl,
            target_disconnected: targetDisconnected,
            target_state_changed: targetStateChanged,
            stable_page_change: pageProof.stable_page_change
        };
        const stateChanged = Boolean(
            valueChanged ||
            verificationSignals.navigation_observed ||
            verificationSignals.url_changed ||
            targetDisconnected ||
            targetStateChanged
        );
        const next = await inspectPage(80, 5000);
        res.json({
            status: 'success',
            action: `Entered ${inputLength} character(s) in ${actedElement.label || descriptor.id}.`,
            dispatched: true,
            outcome_ambiguous: !stateChanged,
            retry_safe: false,
            requires_reinspection: !stateChanged,
            acted_element: actedElement,
            before_hash: beforeHash,
            initial_after_hash: pageProof.initial_after_hash,
            after_hash: pageProof.after_hash,
            verification_signals: verificationSignals,
            state_changed: stateChanged,
            value_changed: valueChanged,
            value_length_changed: valueLengthChanged,
            input_length: inputLength,
            input_sha256: inputDigest,
            ...next
        });
    } catch (error) {
        if (beforeValueState) {
            await beforeValueState.dispose().catch(() => {});
            beforeValueState = null;
        }
        lastError = error.message || String(error);
        if (dispatched) {
            return ambiguousActionError(res, {
                acted_element: actedElement,
                before_hash: beforeHash,
                verification_signals: verificationSignals,
                input_length: inputLength,
                input_sha256: inputDigest
            });
        }
        return res.status(routeErrorStatus(error, 409)).json({
            status: 'error',
            content: lastError,
            dispatched: false,
            outcome_ambiguous: false,
            retry_safe: false,
            requires_reinspection: true,
            acted_element: actedElement,
            before_hash: beforeHash,
            initial_after_hash: '',
            after_hash: '',
            verification_signals: verificationSignals,
            state_changed: false,
            input_length: inputLength,
            input_sha256: inputDigest
        });
    }
});

app.listen(3000, '127.0.0.1', () =>
    console.log('>>> MOLTBOT LISTENING ON 127.0.0.1:3000')
);
