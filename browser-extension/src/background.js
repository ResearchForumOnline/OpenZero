import { requestBrowserAction } from "./shared/openzero-client.js";
import {
  actionPreview,
  classifyBrowserAction,
  isHttpPage,
  mergeSettings,
  normalizeApiBaseUrl,
  originPattern,
  siteOrigin
} from "./shared/policy.js";

const SESSION_KEY = "openzeroTabPilotStateV1";
const SETTINGS_KEY = "settings";
const controllers = new Map();
let stateQueue = Promise.resolve();

function freshState() {
  return {
    version: 1,
    grants: {},
    runs: {},
    pending: {}
  };
}

function normalizeState(value) {
  const state = value && typeof value === "object" ? value : {};
  return {
    version: 1,
    grants: state.grants && typeof state.grants === "object" ? state.grants : {},
    runs: state.runs && typeof state.runs === "object" ? state.runs : {},
    pending: state.pending && typeof state.pending === "object" ? state.pending : {}
  };
}

async function readState() {
  const stored = await chrome.storage.session.get(SESSION_KEY);
  return normalizeState(stored[SESSION_KEY]);
}

function withState(mutator) {
  const operation = stateQueue.then(async () => {
    const state = await readState();
    const result = await mutator(state);
    await chrome.storage.session.set({ [SESSION_KEY]: state });
    return result;
  });
  stateQueue = operation.then(
    () => undefined,
    () => undefined
  );
  return operation;
}

async function getSettings() {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  return mergeSettings(stored[SETTINGS_KEY]);
}

function tabKey(tabId) {
  return String(Number(tabId));
}

function cleanMessage(value, maxLength = 500) {
  return String(value ?? "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function now() {
  return Date.now();
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error("No active Brave tab was found.");
  }
  return tab;
}

async function setBadge(tabId, state) {
  const badge = {
    granted: { text: "ON", color: "#2563eb" },
    running: { text: "RUN", color: "#0891b2" },
    paused: { text: "!", color: "#d97706" },
    done: { text: "OK", color: "#16a34a" },
    error: { text: "ERR", color: "#dc2626" },
    off: { text: "", color: "#64748b" }
  }[state] || { text: "ON", color: "#2563eb" };
  await chrome.action.setBadgeBackgroundColor({ tabId, color: badge.color }).catch(() => {});
  await chrome.action.setBadgeText({ tabId, text: badge.text }).catch(() => {});
}

async function injectController(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/content.js"]
  });
}

async function sendToTab(tabId, message) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (!response?.ok) {
      throw new Error(response?.error || "The page controller rejected the action.");
    }
    return response;
  } catch (firstError) {
    await injectController(tabId);
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (!response?.ok) {
      throw new Error(response?.error || cleanMessage(firstError?.message || firstError));
    }
    return response;
  }
}

async function overlay(tabId, grantId, status, message) {
  if (!grantId) {
    return;
  }
  await sendToTab(tabId, {
    type: "OZ_STATUS",
    grantId,
    status,
    message: cleanMessage(message, 320)
  }).catch(() => {});
}

async function initializeController(tabId, grantId, status = "granted", message = "Tab explicitly granted") {
  await injectController(tabId);
  const response = await chrome.tabs.sendMessage(tabId, {
    type: "OZ_INIT",
    grantId,
    status,
    message
  });
  if (!response?.ok) {
    throw new Error(response?.error || "Could not initialize the page controller.");
  }
}

async function grantActiveTab() {
  const tab = await activeTab();
  if (!isHttpPage(tab.url)) {
    throw new Error("Only normal HTTP(S) pages can be granted. Brave and extension pages are blocked.");
  }
  const key = tabKey(tab.id);
  const grant = {
    grantId: crypto.randomUUID(),
    tabId: tab.id,
    origin: siteOrigin(tab.url),
    url: tab.url,
    grantedAt: now(),
    expectedOrigin: "",
    expectedUntil: 0
  };
  const oldGrant = await withState((state) => {
    const previous = state.grants[key] || null;
    state.grants[key] = grant;
    delete state.pending[key];
    if (state.runs[key]) {
      state.runs[key].status = "stopped";
      state.runs[key].message = "Replaced by a new explicit tab grant.";
      state.runs[key].updatedAt = now();
    }
    return previous;
  });
  if (oldGrant?.grantId) {
    await chrome.tabs
      .sendMessage(tab.id, { type: "OZ_REVOKE", grantId: oldGrant.grantId })
      .catch(() => {});
  }
  await initializeController(tab.id, grant.grantId);
  await setBadge(tab.id, "granted");
  return { ok: true, tabId: tab.id, origin: grant.origin };
}

async function stopTab(tabId, message, revoke = false) {
  const key = tabKey(tabId);
  const controller = controllers.get(key);
  if (controller) {
    controller.abort();
    controllers.delete(key);
  }
  const result = await withState((state) => {
    const grant = state.grants[key] || null;
    const run = state.runs[key] || null;
    if (run) {
      run.status = "stopped";
      run.message = cleanMessage(message, 320) || "Stopped by the user.";
      run.updatedAt = now();
    }
    delete state.pending[key];
    if (revoke) {
      delete state.grants[key];
    }
    return { grant, run };
  });
  if (revoke && result.grant?.grantId) {
    await chrome.tabs
      .sendMessage(tabId, { type: "OZ_REVOKE", grantId: result.grant.grantId })
      .catch(() => {});
    await setBadge(tabId, "off");
  } else if (result.grant?.grantId) {
    await overlay(tabId, result.grant.grantId, "paused", message || "Run stopped");
    await setBadge(tabId, "paused");
  }
  return { ok: true };
}

async function revokeActiveTab() {
  const tab = await activeTab();
  return stopTab(tab.id, "Access revoked by the user.", true);
}

async function assertCurrentGrant(tabId) {
  const key = tabKey(tabId);
  const tab = await chrome.tabs.get(tabId);
  if (!isHttpPage(tab.url)) {
    throw new Error("The granted tab is no longer on a normal HTTP(S) page.");
  }
  const currentOrigin = siteOrigin(tab.url);
  return withState((state) => {
    const grant = state.grants[key];
    if (!grant) {
      throw new Error("Grant this tab before starting OpenZero.");
    }
    if (grant.origin !== currentOrigin) {
      if (grant.expectedOrigin === currentOrigin && Number(grant.expectedUntil || 0) > now()) {
        grant.origin = currentOrigin;
        grant.url = tab.url;
        grant.expectedOrigin = "";
        grant.expectedUntil = 0;
      } else {
        throw new Error("The tab changed site, so its explicit grant was revoked.");
      }
    }
    return { grant: { ...grant }, tab };
  });
}

async function ensureApiPermission(settings) {
  const apiOrigin = normalizeApiBaseUrl(settings.apiBaseUrl);
  const pattern = originPattern(apiOrigin);
  const allowed = await chrome.permissions.contains({ origins: [pattern] });
  if (!allowed) {
    throw new Error("Open extension options and grant access to the configured OpenZero API origin.");
  }
  return apiOrigin;
}

function publicPending(pending) {
  if (!pending) {
    return null;
  }
  return {
    kind: pending.kind,
    preview: pending.preview,
    destinationOrigin: pending.destinationOrigin || "",
    destinationUrl: pending.destinationUrl || "",
    pattern: pending.pattern || "",
    expiresAt: pending.expiresAt,
    needsApprovalAfterSite: Boolean(pending.needsApprovalAfterSite)
  };
}

async function getPopupStatus() {
  const tab = await activeTab();
  const key = tabKey(tab.id);
  const settings = await getSettings();
  const state = await readState();
  const grant = state.grants[key] || null;
  const run = state.runs[key] || null;
  const pending = state.pending[key] || null;
  const currentOrigin = isHttpPage(tab.url) ? siteOrigin(tab.url) : "";
  const pagePattern = currentOrigin ? `${currentOrigin}/*` : "";
  const sitePermission = pagePattern
    ? await chrome.permissions.contains({ origins: [pagePattern] }).catch(() => false)
    : false;

  return {
    ok: true,
    tab: {
      id: tab.id,
      title: cleanMessage(tab.title, 180),
      url: tab.url || "",
      origin: currentOrigin,
      supported: isHttpPage(tab.url)
    },
    granted: Boolean(grant && grant.origin === currentOrigin),
    grant: grant
      ? {
          origin: grant.origin,
          grantedAt: grant.grantedAt
        }
      : null,
    run: run
      ? {
          status: run.status,
          step: run.step,
          maxSteps: run.maxSteps,
          message: run.message,
          task: cleanMessage(run.task, 160),
          updatedAt: run.updatedAt
        }
      : null,
    pending: publicPending(pending),
    sitePermission,
    pagePattern,
    api: {
      configured: Boolean(settings.apiKey && settings.apiBaseUrl && settings.model),
      baseUrl: settings.apiBaseUrl,
      model: settings.model,
      hasKey: Boolean(settings.apiKey)
    }
  };
}

function appendHistory(run, actionName, result) {
  run.history = Array.isArray(run.history) ? run.history : [];
  run.history.push({
    action: cleanMessage(actionName, 32),
    result: cleanMessage(result, 500)
  });
  run.history = run.history.slice(-8);
}

async function setRunMessage(tabId, status, message, extra = {}) {
  const key = tabKey(tabId);
  return withState((state) => {
    const run = state.runs[key];
    if (!run) {
      throw new Error("The browser run no longer exists.");
    }
    Object.assign(run, extra);
    run.status = status;
    run.message = cleanMessage(message, 500);
    run.updatedAt = now();
    return { run: { ...run }, grant: state.grants[key] ? { ...state.grants[key] } : null };
  });
}

async function inspect(tabId, grantId) {
  await initializeController(tabId, grantId, "running", "OpenZero is inspecting this tab");
  const response = await sendToTab(tabId, {
    type: "OZ_INSPECT",
    grantId
  });
  if (!response.snapshot || response.snapshot.url !== (await chrome.tabs.get(tabId)).url) {
    throw new Error("The page changed while it was being inspected.");
  }
  return response.snapshot;
}

function waitForTabComplete(tabId, timeoutMs = 20000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (result) => {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(result);
    };
    const listener = (changedTabId, changeInfo) => {
      if (changedTabId === tabId && changeInfo.status === "complete") {
        finish(true);
      }
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs
      .get(tabId)
      .then((tab) => {
        if (tab.status === "complete") {
          finish(true);
        }
      })
      .catch(() => finish(false));
  });
}

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function executeAction(tabId, grantId, action, snapshotId) {
  if (action.action === "wait") {
    await pause(action.ms);
    return `Waited ${action.ms} ms.`;
  }
  if (action.action === "navigate") {
    await chrome.tabs.update(tabId, { url: action.url });
    await waitForTabComplete(tabId);
    return `Navigation requested: ${action.url}`;
  }
  if (action.action === "back") {
    await chrome.tabs.goBack(tabId);
    await waitForTabComplete(tabId);
    return "Back navigation requested.";
  }
  if (action.action === "forward") {
    await chrome.tabs.goForward(tabId);
    await waitForTabComplete(tabId);
    return "Forward navigation requested.";
  }

  try {
    const response = await sendToTab(tabId, {
      type: "OZ_EXECUTE",
      grantId,
      action: { ...action, snapshot_id: snapshotId }
    });
    if (action.action === "click") {
      await pause(700);
    }
    return cleanMessage(response.result, 500) || `${action.action} dispatched.`;
  } catch (error) {
    if (action.action === "click" && /message port|receiving end|context invalidated/i.test(String(error))) {
      await pause(700);
      return "Click dispatched; the page navigated before it could acknowledge the action.";
    }
    throw error;
  }
}

async function recordExecution(tabId, action, result) {
  const key = tabKey(tabId);
  await withState((state) => {
    const run = state.runs[key];
    if (!run) {
      throw new Error("The browser run no longer exists.");
    }
    appendHistory(run, action.action, result);
    run.message = cleanMessage(result, 500);
    run.updatedAt = now();
  });
}

async function createPending(tabId, runId, action, snapshot, decision) {
  const key = tabKey(tabId);
  const kind = decision.needsSiteConsent ? "site" : "risk";
  const destinationUrl = decision.destinationUrl || "";
  const destinationOrigin = siteOrigin(destinationUrl);
  const pending = {
    kind,
    runId,
    tabId,
    action,
    snapshotId: snapshot.snapshot_id,
    preview: actionPreview(action, snapshot),
    destinationUrl,
    destinationOrigin,
    pattern: destinationOrigin ? `${destinationOrigin}/*` : "",
    needsApprovalAfterSite: Boolean(decision.needsSiteConsent && decision.needsApproval),
    createdAt: now(),
    expiresAt: now() + 10 * 60 * 1000
  };
  await withState((state) => {
    const run = state.runs[key];
    if (!run || run.runId !== runId) {
      throw new Error("The browser run no longer exists.");
    }
    run.status = "paused";
    run.message =
      kind === "site"
        ? `Site permission required for ${destinationOrigin}.`
        : `Human confirmation required: ${pending.preview}`;
    run.updatedAt = now();
    state.pending[key] = pending;
  });
  const grant = (await readState()).grants[key];
  await overlay(
    tabId,
    grant?.grantId,
    "paused",
    kind === "site"
      ? `Paused: approve ${destinationOrigin} in the extension`
      : `Paused: approve once in the extension`
  );
  await setBadge(tabId, "paused");
  return { ok: true, paused: true, pending: publicPending(pending) };
}

async function finishRun(tabId, status, message) {
  const result = await setRunMessage(tabId, status, message);
  const overlayState = status === "completed" ? "done" : status === "error" ? "error" : "paused";
  await overlay(tabId, result.grant?.grantId, overlayState, message);
  await setBadge(tabId, status === "completed" ? "done" : status === "error" ? "error" : "paused");
  return { ok: status === "completed", status, message };
}

async function runLoop(tabId, runId) {
  const key = tabKey(tabId);
  try {
    while (true) {
      const state = await readState();
      const run = state.runs[key];
      if (!run || run.runId !== runId) {
        throw new Error("The browser run was replaced.");
      }
      if (run.status !== "running") {
        return { ok: true, status: run.status, message: run.message };
      }
      if (run.step >= run.maxSteps) {
        return finishRun(
          tabId,
          "limit",
          `Stopped safely at the ${run.maxSteps}-step limit. Review the page and start again if needed.`
        );
      }

      const { grant } = await assertCurrentGrant(tabId);
      await setBadge(tabId, "running");
      await overlay(tabId, grant.grantId, "running", `Working · step ${run.step + 1}/${run.maxSteps}`);
      const snapshot = await inspect(tabId, grant.grantId);

      const latest = await withState((mutable) => {
        const current = mutable.runs[key];
        if (!current || current.runId !== runId || current.status !== "running") {
          throw new Error("The run was stopped before model planning.");
        }
        current.step += 1;
        current.message = `Planning step ${current.step}/${current.maxSteps}.`;
        current.updatedAt = now();
        return { ...current, history: [...(current.history || [])] };
      });

      const settings = await getSettings();
      await ensureApiPermission(settings);
      const controller = new AbortController();
      controllers.set(key, controller);
      const timeout = setTimeout(
        () => controller.abort(new Error("OpenZero request timed out.")),
        settings.requestTimeoutSeconds * 1000
      );
      let action;
      try {
        action = await requestBrowserAction({
          settings,
          task: latest.task,
          snapshot,
          step: latest.step,
          history: latest.history,
          signal: controller.signal
        });
      } finally {
        clearTimeout(timeout);
        if (controllers.get(key) === controller) {
          controllers.delete(key);
        }
      }

      const afterModel = await readState();
      if (afterModel.runs[key]?.status !== "running") {
        return {
          ok: true,
          status: afterModel.runs[key]?.status || "stopped",
          message: afterModel.runs[key]?.message || "Stopped."
        };
      }
      if (action.action === "finish") {
        return finishRun(tabId, "completed", action.message);
      }

      const decision = classifyBrowserAction(action, snapshot, settings);
      if (!decision.allowed) {
        await recordExecution(tabId, action, `Policy denied: ${decision.reason}`);
        await overlay(tabId, grant.grantId, "running", `Policy denied ${action.action}; replanning`);
        continue;
      }
      if (decision.needsSiteConsent || decision.needsApproval) {
        return createPending(tabId, runId, action, snapshot, decision);
      }

      const executionResult = await executeAction(tabId, grant.grantId, action, snapshot.snapshot_id);
      await recordExecution(tabId, action, executionResult);
    }
  } catch (error) {
    const state = await readState();
    const run = state.runs[key];
    if (run?.status === "stopped") {
      return { ok: true, status: "stopped", message: run.message };
    }
    const isAbort = error?.name === "AbortError" || /aborted|timed out/i.test(String(error?.message || error));
    const message = isAbort
      ? "OpenZero browser run stopped or timed out."
      : cleanMessage(error?.message || error, 500);
    return finishRun(tabId, "error", message);
  }
}

async function startTask(taskText) {
  const tab = await activeTab();
  const task = cleanMessage(taskText, 3000);
  if (!task) {
    throw new Error("Describe the work OpenZero should do in this tab.");
  }
  const { grant } = await assertCurrentGrant(tab.id);
  const settings = await getSettings();
  await ensureApiPermission(settings);
  if (!settings.apiKey) {
    throw new Error("Set the OpenZero API key in extension options.");
  }
  const key = tabKey(tab.id);
  const run = {
    runId: crypto.randomUUID(),
    tabId: tab.id,
    grantId: grant.grantId,
    task,
    status: "running",
    step: 0,
    maxSteps: settings.maxSteps,
    history: [],
    message: "Starting OpenZero browser work.",
    startedAt: now(),
    updatedAt: now()
  };
  await withState((state) => {
    state.runs[key] = run;
    delete state.pending[key];
  });
  await overlay(tab.id, grant.grantId, "running", "Starting OpenZero browser work");
  await setBadge(tab.id, "running");
  return runLoop(tab.id, run.runId);
}

async function approveRisk() {
  const tab = await activeTab();
  const key = tabKey(tab.id);
  const state = await readState();
  const pending = state.pending[key];
  const run = state.runs[key];
  const grant = state.grants[key];
  if (!pending || pending.kind !== "risk" || !run || !grant) {
    throw new Error("There is no pending action to approve.");
  }
  if (pending.expiresAt <= now()) {
    await stopTab(tab.id, "Pending approval expired.", false);
    throw new Error("The pending action expired. Start the task again.");
  }
  await assertCurrentGrant(tab.id);
  await withState((mutable) => {
    const current = mutable.runs[key];
    const currentGrant = mutable.grants[key];
    if (!current || current.runId !== pending.runId) {
      throw new Error("The pending action does not match the current run.");
    }
    if (!currentGrant) {
      throw new Error("The tab grant no longer exists.");
    }
    current.status = "running";
    current.message = `Human approved once: ${pending.preview}`;
    current.updatedAt = now();
    if (pending.siteApprovedOrigin) {
      currentGrant.expectedOrigin = pending.siteApprovedOrigin;
      currentGrant.expectedUntil = now() + 60 * 1000;
    }
    delete mutable.pending[key];
  });
  const action = { ...pending.action, confirmed: true };
  const result = await executeAction(tab.id, grant.grantId, action, pending.snapshotId);
  await recordExecution(tab.id, action, `Human approved once. ${result}`);
  return runLoop(tab.id, run.runId);
}

async function denyPending() {
  const tab = await activeTab();
  const key = tabKey(tab.id);
  const state = await readState();
  const pending = state.pending[key];
  const run = state.runs[key];
  if (!pending || !run) {
    throw new Error("There is no pending action to deny.");
  }
  await withState((mutable) => {
    const current = mutable.runs[key];
    if (!current || current.runId !== pending.runId) {
      throw new Error("The pending action does not match the current run.");
    }
    appendHistory(current, pending.action.action, `Human denied: ${pending.preview}`);
    current.status = "running";
    current.message = `Human denied ${pending.action.action}; asking OpenZero for a safer alternative.`;
    current.updatedAt = now();
    delete mutable.pending[key];
  });
  return runLoop(tab.id, run.runId);
}

async function approveSite(pattern) {
  const tab = await activeTab();
  const key = tabKey(tab.id);
  const state = await readState();
  const pending = state.pending[key];
  const run = state.runs[key];
  const grant = state.grants[key];
  if (!pending || pending.kind !== "site" || !run || !grant) {
    throw new Error("There is no pending site permission request.");
  }
  if (pending.expiresAt <= now()) {
    await stopTab(tab.id, "Pending site consent expired.", false);
    throw new Error("The pending site consent expired. Start the task again.");
  }
  if (!pending.pattern || pending.pattern !== pattern) {
    throw new Error("The granted origin does not match the pending destination.");
  }
  const permissionExists = await chrome.permissions.contains({ origins: [pending.pattern] });
  if (!permissionExists) {
    throw new Error("Brave did not grant the requested destination permission.");
  }

  if (pending.needsApprovalAfterSite) {
    await withState((mutable) => {
      const current = mutable.runs[key];
      if (!current || current.runId !== pending.runId) {
        throw new Error("The pending site action no longer matches the run.");
      }
      current.status = "paused";
      current.message = `Site allowed. Human action confirmation still required: ${pending.preview}`;
      current.updatedAt = now();
      mutable.pending[key] = {
        ...pending,
        kind: "risk",
        pattern: "",
        destinationOrigin: "",
        destinationUrl: "",
        needsApprovalAfterSite: false,
        siteApprovedOrigin: pending.destinationOrigin
      };
    });
    await overlay(tab.id, grant.grantId, "paused", "Site allowed · action approval still required");
    return { ok: true, paused: true };
  }

  await withState((mutable) => {
    const current = mutable.runs[key];
    const currentGrant = mutable.grants[key];
    if (!current || current.runId !== pending.runId || !currentGrant) {
      throw new Error("The pending site action no longer matches the run.");
    }
    current.status = "running";
    current.message = `Site allowed: ${pending.destinationOrigin}`;
    current.updatedAt = now();
    currentGrant.expectedOrigin = pending.destinationOrigin;
    currentGrant.expectedUntil = now() + 60 * 1000;
    delete mutable.pending[key];
  });
  const result = await executeAction(tab.id, grant.grantId, pending.action, pending.snapshotId);
  await recordExecution(tab.id, pending.action, `Site allowed. ${result}`);
  return runLoop(tab.id, run.runId);
}

async function revokeCurrentSite(pattern) {
  const tab = await activeTab();
  const key = tabKey(tab.id);
  const expected = isHttpPage(tab.url) ? originPattern(tab.url) : "";
  if (!pattern || pattern !== expected) {
    throw new Error("Site revocation target does not match the active tab.");
  }
  await chrome.permissions.remove({ origins: [pattern] });
  const state = await readState();
  if (state.grants[key]?.origin === siteOrigin(tab.url)) {
    await stopTab(tab.id, "Tab and site access revoked by the user.", true);
  }
  return { ok: true };
}

async function routeMessage(message, sender) {
  switch (message?.type) {
    case "GET_STATUS":
      return getPopupStatus();
    case "GRANT_ACTIVE_TAB":
      return grantActiveTab();
    case "REVOKE_ACTIVE_TAB":
      return revokeActiveTab();
    case "START_TASK":
      return startTask(message.task);
    case "STOP_ACTIVE_RUN": {
      const tab = await activeTab();
      return stopTab(tab.id, "Stopped by the user.", false);
    }
    case "APPROVE_RISK":
      return approveRisk();
    case "DENY_PENDING":
      return denyPending();
    case "APPROVE_SITE":
      return approveSite(String(message.pattern || ""));
    case "REVOKE_SITE":
      return revokeCurrentSite(String(message.pattern || ""));
    case "OVERLAY_STOP":
      if (!sender.tab?.id) {
        throw new Error("Stop request did not come from a granted tab.");
      }
      return stopTab(sender.tab.id, "Stopped and revoked from the on-page control.", true);
    default:
      throw new Error("Unknown OpenZero Tab Pilot command.");
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  routeMessage(message, sender)
    .then((result) => sendResponse(result))
    .catch((error) => sendResponse({ ok: false, error: cleanMessage(error?.message || error, 500) }));
  return true;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!changeInfo.url) {
    return;
  }
  const key = tabKey(tabId);
  const supported = isHttpPage(changeInfo.url);
  const nextOrigin = supported ? siteOrigin(changeInfo.url) : "";
  withState((state) => {
    const grant = state.grants[key];
    if (!grant) {
      return { revoke: false, grant: null };
    }
    if (!supported) {
      const oldGrant = { ...grant };
      delete state.grants[key];
      delete state.pending[key];
      if (state.runs[key]) {
        state.runs[key].status = "stopped";
        state.runs[key].message = "Tab left HTTP(S); explicit tab access was revoked.";
        state.runs[key].updatedAt = now();
      }
      return { revoke: true, grant: oldGrant };
    }
    if (grant.origin === nextOrigin) {
      grant.url = changeInfo.url;
      return { revoke: false, grant: { ...grant } };
    }
    if (grant.expectedOrigin === nextOrigin && Number(grant.expectedUntil || 0) > now()) {
      grant.origin = nextOrigin;
      grant.url = changeInfo.url;
      grant.expectedOrigin = "";
      grant.expectedUntil = 0;
      return { revoke: false, expected: true, grant: { ...grant } };
    }
    const oldGrant = { ...grant };
    delete state.grants[key];
    delete state.pending[key];
    if (state.runs[key]) {
      state.runs[key].status = "stopped";
      state.runs[key].message = "Tab navigated to a different site; explicit tab access was revoked.";
      state.runs[key].updatedAt = now();
    }
    return { revoke: true, grant: oldGrant };
  })
    .then(async (result) => {
      if (result?.revoke) {
        controllers.get(key)?.abort();
        controllers.delete(key);
        await setBadge(tabId, "off");
      } else if (result?.expected && tab.status === "complete") {
        await initializeController(tabId, result.grant.grantId, "running", "Approved site loaded").catch(
          () => {}
        );
      }
    })
    .catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const key = tabKey(tabId);
  controllers.get(key)?.abort();
  controllers.delete(key);
  withState((state) => {
    delete state.grants[key];
    delete state.runs[key];
    delete state.pending[key];
  }).catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  Promise.all([
    chrome.storage.local.get(SETTINGS_KEY).then((stored) => {
      if (!stored[SETTINGS_KEY]) {
        return chrome.storage.local.set({ [SETTINGS_KEY]: mergeSettings() });
      }
      return undefined;
    }),
    chrome.storage.session.set({ [SESSION_KEY]: freshState() })
  ]).catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  chrome.storage.session.set({ [SESSION_KEY]: freshState() }).catch(() => {});
});
