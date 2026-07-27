(() => {
  if (globalThis.__openzeroTabPilotLoaded) {
    return;
  }
  globalThis.__openzeroTabPilotLoaded = true;

  const state = {
    grantId: "",
    snapshotId: "",
    elements: new Map(),
    overlayHost: null,
    overlayParts: null
  };

  const RISKY_LABEL_RE =
    /\b(?:apply|authorize|book|buy|cancel(?:\s+(?:account|plan|subscription))?|checkout|confirm|delete|grant|install|log\s*in|order|pay|post|publish|purchase|remove|reserve|send|sign(?:\s+(?:in|up))?|submit|subscribe|transfer|upload)\b/i;
  const INTERACTIVE_SELECTOR = [
    "a[href]",
    "button",
    "input:not([type='hidden'])",
    "textarea",
    "select",
    "summary",
    "[role='button']",
    "[role='link']",
    "[contenteditable='true']"
  ].join(",");

  function cleanText(value, maxLength = 500) {
    return String(value ?? "")
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, maxLength);
  }

  function isVisible(element) {
    if (!(element instanceof Element) || !element.isConnected) {
      return false;
    }
    const style = getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number.parseFloat(style.opacity || "1") < 0.02
    ) {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  }

  function labelFor(element) {
    const aria = element.getAttribute("aria-label");
    if (aria) {
      return cleanText(aria, 180);
    }
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const text = labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id)?.innerText || "")
        .join(" ");
      if (text.trim()) {
        return cleanText(text, 180);
      }
    }
    if (element.labels?.length) {
      return cleanText(
        Array.from(element.labels)
          .map((label) => label.innerText || label.textContent || "")
          .join(" "),
        180
      );
    }
    if (
      element instanceof HTMLInputElement &&
      ["button", "submit", "reset", "image"].includes(String(element.type || "").toLowerCase()) &&
      element.value
    ) {
      return cleanText(element.value, 180);
    }
    return cleanText(
      element.getAttribute("placeholder") ||
        element.getAttribute("title") ||
        element.innerText ||
        element.textContent ||
        "",
      180
    );
  }

  function sensitiveKindFor(element, label) {
    const type = cleanText(element.getAttribute("type"), 40).toLowerCase();
    const autocomplete = cleanText(element.getAttribute("autocomplete"), 120).toLowerCase();
    const name = cleanText(element.getAttribute("name"), 120).toLowerCase();
    const id = cleanText(element.id, 120).toLowerCase();
    const haystack = `${type} ${autocomplete} ${name} ${id} ${String(label).toLowerCase()}`;

    if (type === "file") {
      return "file";
    }
    if (/\b(?:captcha|hcaptcha|recaptcha|turnstile|not\s+a\s+robot)\b/.test(haystack)) {
      return "captcha";
    }
    if (
      type === "password" ||
      /\b(?:current-password|new-password|password|passcode|one-time-code|otp)\b/.test(haystack)
    ) {
      return "password";
    }
    if (
      /\b(?:cc-number|cc-csc|cc-exp|credit\s*card|debit\s*card|card\s*number|cvv|cvc|payment)\b/.test(
        haystack
      )
    ) {
      return "payment";
    }
    if (/\b(?:api[-_ ]?key|private[-_ ]?key|secret|access[-_ ]?token|auth[-_ ]?token)\b/.test(haystack)) {
      return "secret";
    }
    if (
      [
        "email",
        "tel",
        "street-address",
        "address-line1",
        "address-line2",
        "postal-code",
        "country",
        "name",
        "given-name",
        "family-name",
        "bday"
      ].some((marker) => autocomplete.split(/\s+/).includes(marker)) ||
      ["email", "tel"].includes(type)
    ) {
      return "personal";
    }
    return "";
  }

  function descriptorFor(element, id) {
    const label = labelFor(element);
    const text = cleanText(element.innerText || element.textContent || "", 220);
    let href = "";
    if (element instanceof HTMLAnchorElement && element.href) {
      href = cleanText(element.href, 1000);
    }
    const isSubmitControl =
      (element instanceof HTMLInputElement && ["submit", "image"].includes(element.type)) ||
      (element instanceof HTMLButtonElement &&
        Boolean(element.form) &&
        (!element.getAttribute("type") || element.type === "submit"));
    const options =
      element instanceof HTMLSelectElement
        ? Array.from(element.options)
            .slice(0, 30)
            .map((option) => ({
              value: cleanText(option.value, 200),
              label: cleanText(option.textContent, 200)
            }))
        : undefined;
    const rect = element.getBoundingClientRect();
    const sensitiveKind = sensitiveKindFor(element, label);
    return {
      id,
      tag: element.tagName.toLowerCase(),
      role: cleanText(element.getAttribute("role"), 40),
      type: cleanText(element.getAttribute("type"), 40),
      label,
      text,
      href,
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      checked:
        typeof element.checked === "boolean" && ["checkbox", "radio"].includes(element.type)
          ? element.checked
          : undefined,
      has_value:
        element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement
          ? Boolean(element.value)
          : undefined,
      options,
      sensitive_kind: sensitiveKind,
      risk:
        isSubmitControl || RISKY_LABEL_RE.test(`${label} ${text} ${href}`)
          ? "consequential"
          : "",
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    };
  }

  function pageText() {
    const root = document.body?.cloneNode(true);
    if (!root) {
      return "";
    }
    root.querySelectorAll("script,style,noscript,svg,canvas,[data-openzero-tab-pilot]").forEach((node) => {
      node.remove();
    });
    return cleanText(root.innerText || root.textContent || "", 12000);
  }

  function inspectPage() {
    state.elements.clear();
    state.snapshotId = crypto.randomUUID();
    const interactive = [];
    const candidates = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR)).filter(
      (element) =>
        !element.closest("[data-openzero-tab-pilot]") &&
        isVisible(element) &&
        !element.matches("[inert]") &&
        !element.closest("[inert]")
    );
    for (const element of candidates.slice(0, 120)) {
      const id = `e${interactive.length + 1}`;
      state.elements.set(id, element);
      interactive.push(descriptorFor(element, id));
    }
    const headings = Array.from(document.querySelectorAll("h1,h2,h3,[role='heading']"))
      .filter(isVisible)
      .slice(0, 40)
      .map((heading) => ({
        level: Number.parseInt(heading.getAttribute("aria-level"), 10) ||
          Number.parseInt(heading.tagName.slice(1), 10) ||
          0,
        text: cleanText(heading.innerText || heading.textContent || "", 240)
      }))
      .filter((heading) => heading.text);

    return {
      snapshot_id: state.snapshotId,
      url: location.href,
      title: cleanText(document.title, 300),
      text: pageText(),
      headings,
      interactive,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        scroll_x: Math.round(window.scrollX),
        scroll_y: Math.round(window.scrollY),
        page_height: Math.round(document.documentElement.scrollHeight)
      }
    };
  }

  function ensureOverlay() {
    if (state.overlayHost?.isConnected && state.overlayParts) {
      return state.overlayParts;
    }
    const host = document.createElement("div");
    host.dataset.openzeroTabPilot = "status";
    host.style.setProperty("all", "initial", "important");
    host.style.setProperty("position", "fixed", "important");
    host.style.setProperty("top", "12px", "important");
    host.style.setProperty("right", "12px", "important");
    host.style.setProperty("z-index", "2147483647", "important");
    const shadow = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      .card {
        width: 260px; box-sizing: border-box; border-radius: 12px; padding: 11px 12px;
        color: #f8fafc; background: #111827; border: 2px solid #60a5fa;
        box-shadow: 0 10px 35px rgba(0,0,0,.42); font: 600 13px/1.35 system-ui,sans-serif;
      }
      .top { display:flex; align-items:center; gap:8px; }
      .dot { width:10px; height:10px; flex:none; border-radius:50%; background:#60a5fa; }
      .title { flex:1; letter-spacing:.01em; }
      .status { margin-top:7px; color:#e5e7eb; font-weight:500; overflow-wrap:anywhere; }
      button {
        margin-top:9px; width:100%; padding:7px 9px; border:1px solid #fca5a5; border-radius:8px;
        background:#7f1d1d; color:#fff; font:700 12px system-ui,sans-serif; cursor:pointer;
      }
      button:hover, button:focus { background:#991b1b; outline:2px solid #fff; outline-offset:2px; }
      .running { border-color:#22d3ee; } .running .dot { background:#22d3ee; animation:pulse 1s infinite; }
      .paused { border-color:#fbbf24; } .paused .dot { background:#fbbf24; }
      .error { border-color:#f87171; } .error .dot { background:#f87171; }
      .done { border-color:#4ade80; } .done .dot { background:#4ade80; }
      .revoked { border-color:#94a3b8; } .revoked .dot { background:#94a3b8; }
      @keyframes pulse { 50% { opacity:.35; } }
      @media (prefers-reduced-motion: reduce) { .running .dot { animation:none; } }
    `;
    const card = document.createElement("section");
    card.className = "card";
    card.setAttribute("aria-live", "polite");
    const top = document.createElement("div");
    top.className = "top";
    const dot = document.createElement("span");
    dot.className = "dot";
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = "OpenZero Tab Pilot";
    const status = document.createElement("div");
    status.className = "status";
    status.textContent = "Tab granted";
    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "STOP AND REVOKE TAB";
    stop.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "OVERLAY_STOP", grantId: state.grantId }).catch(() => {});
    });
    top.append(dot, title);
    card.append(top, status, stop);
    shadow.append(style, card);
    (document.documentElement || document.body).append(host);
    state.overlayHost = host;
    state.overlayParts = { card, status, stop };
    return state.overlayParts;
  }

  function updateOverlay(status, message) {
    const parts = ensureOverlay();
    parts.card.className = `card ${cleanText(status, 20)}`;
    parts.status.textContent = cleanText(message, 320) || "OpenZero Tab Pilot active";
    parts.stop.hidden = status === "revoked";
  }

  function removeOverlay() {
    state.overlayHost?.remove();
    state.overlayHost = null;
    state.overlayParts = null;
  }

  function assertGrant(message) {
    if (!state.grantId || !message.grantId || message.grantId !== state.grantId) {
      throw new Error("Tab grant is missing or stale.");
    }
  }

  function currentElement(action) {
    if (action.snapshot_id !== state.snapshotId) {
      throw new Error("Page snapshot is stale; inspect again.");
    }
    const element = state.elements.get(action.element_id);
    if (!element || !element.isConnected || !isVisible(element)) {
      throw new Error("Target element is no longer available; inspect again.");
    }
    return element;
  }

  function dispatchInputEvents(element) {
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setNativeValue(element, value) {
    const prototype =
      element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (descriptor?.set) {
      descriptor.set.call(element, value);
    } else {
      element.value = value;
    }
  }

  async function executeAction(action) {
    if (action.action === "scroll") {
      if (action.direction === "top") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else if (action.direction === "bottom") {
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
      } else {
        const amount = action.direction === "up" ? -action.amount : action.amount;
        window.scrollBy({ top: amount, behavior: "smooth" });
      }
      return { ok: true, result: `Scrolled ${action.direction}.` };
    }

    const element = currentElement(action);
    const descriptor = descriptorFor(element, action.element_id);
    if (descriptor.disabled) {
      throw new Error("Target element is disabled.");
    }

    if (action.action === "click") {
      if (
        descriptor.href &&
        !/^https?:/i.test(descriptor.href) &&
        !descriptor.href.startsWith("#")
      ) {
        throw new Error("Non-HTTP link actions are blocked.");
      }
      if (descriptor.risk === "consequential" && !action.confirmed) {
        throw new Error("This click still requires explicit confirmation.");
      }
      element.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
      element.focus({ preventScroll: true });
      element.click();
      return { ok: true, result: `Clicked ${descriptor.label || action.element_id}.` };
    }

    if (["password", "payment", "secret", "file", "captcha"].includes(descriptor.sensitive_kind)) {
      throw new Error(`Typing into ${descriptor.sensitive_kind} fields is blocked.`);
    }

    if (action.action === "type") {
      if (
        !(
          element instanceof HTMLInputElement ||
          element instanceof HTMLTextAreaElement ||
          element.isContentEditable
        )
      ) {
        throw new Error("Target is not a text-editable element.");
      }
      element.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
      element.focus({ preventScroll: true });
      if (element.isContentEditable) {
        if (action.clear) {
          element.textContent = "";
        }
        element.textContent = `${action.clear ? "" : element.textContent || ""}${action.text}`;
        dispatchInputEvents(element);
      } else {
        const nextValue = `${action.clear ? "" : element.value || ""}${action.text}`;
        setNativeValue(element, nextValue);
        dispatchInputEvents(element);
      }
      return {
        ok: true,
        result: `Entered ${String(action.text || "").length} character(s) in ${descriptor.label || action.element_id}.`
      };
    }

    if (action.action === "select") {
      if (!(element instanceof HTMLSelectElement)) {
        throw new Error("Target is not a select element.");
      }
      const option = Array.from(element.options).find(
        (candidate) =>
          candidate.value === action.value ||
          cleanText(candidate.textContent, 500).toLowerCase() ===
            cleanText(action.value, 500).toLowerCase()
      );
      if (!option) {
        throw new Error("Requested option is not available.");
      }
      element.value = option.value;
      dispatchInputEvents(element);
      return { ok: true, result: `Selected ${cleanText(option.textContent, 120)}.` };
    }

    throw new Error(`Unsupported content action: ${action.action}`);
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    Promise.resolve()
      .then(async () => {
        if (!message || typeof message !== "object") {
          return { ok: false, error: "Invalid extension message." };
        }
        if (message.type === "OZ_INIT") {
          state.grantId = String(message.grantId || "");
          updateOverlay(message.status || "granted", message.message || "Tab explicitly granted");
          return { ok: true, url: location.href };
        }
        if (message.type === "OZ_REVOKE") {
          if (!message.grantId || message.grantId === state.grantId) {
            state.grantId = "";
            state.snapshotId = "";
            state.elements.clear();
            updateOverlay("revoked", "OpenZero access revoked");
            setTimeout(removeOverlay, 1800);
          }
          return { ok: true };
        }
        assertGrant(message);
        if (message.type === "OZ_STATUS") {
          updateOverlay(message.status || "granted", message.message || "OpenZero Tab Pilot active");
          return { ok: true };
        }
        if (message.type === "OZ_INSPECT") {
          return { ok: true, snapshot: inspectPage() };
        }
        if (message.type === "OZ_EXECUTE") {
          const result = await executeAction(message.action || {});
          return { ...result, url: location.href };
        }
        return { ok: false, error: "Unknown extension message." };
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: cleanText(error?.message || error, 500) }));
    return true;
  });
})();
