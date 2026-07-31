export const DEFAULT_SETTINGS = Object.freeze({
  apiBaseUrl: "http://127.0.0.1:1024",
  apiKey: "",
  model: "openzerogemma:latest",
  maxSteps: 12,
  requestTimeoutSeconds: 120,
  allowNavigation: true,
  allowClicking: true,
  allowTyping: true,
  requireRiskApproval: true,
  openzeroSpark: "auto"
});

export const ACTION_NAMES = Object.freeze([
  "finish",
  "navigate",
  "click",
  "type",
  "select",
  "scroll",
  "wait",
  "back",
  "forward"
]);

const ACTION_SET = new Set(ACTION_NAMES);
const ELEMENT_ID_RE = /^e[1-9]\d{0,3}$/;
const RISKY_LABEL_RE =
  /\b(?:apply|authorize|book|buy|cancel(?:\s+(?:account|plan|subscription))?|checkout|confirm|delete|grant|install|log\s*in|order|pay|post|publish|purchase|remove|reserve|send|sign(?:\s+(?:in|up))?|submit|subscribe|transfer|upload)\b/i;
const BLOCKED_SCHEMES_RE = /^(?:javascript|data|file|chrome|brave|edge|about|view-source|blob):/i;
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

function compactText(value, maxLength) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function requireElementId(value) {
  const elementId = compactText(value, 16);
  if (!ELEMENT_ID_RE.test(elementId)) {
    throw new Error("A current snapshot element_id such as e3 is required.");
  }
  return elementId;
}

export function isHttpPage(rawUrl) {
  try {
    const parsed = new URL(String(rawUrl || ""));
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function siteOrigin(rawUrl) {
  if (!isHttpPage(rawUrl)) {
    return "";
  }
  return new URL(rawUrl).origin;
}

export function originPattern(rawUrl) {
  const origin = siteOrigin(rawUrl);
  return origin ? `${origin}/*` : "";
}

export function sameOrigin(firstUrl, secondUrl) {
  const first = siteOrigin(firstUrl);
  const second = siteOrigin(secondUrl);
  return Boolean(first && second && first === second);
}

export function normalizeApiBaseUrl(rawUrl) {
  const value = compactText(rawUrl, 500);
  if (!value) {
    throw new Error("OpenZero API URL is required.");
  }
  const parsed = new URL(value);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("OpenZero API URL must use HTTP or HTTPS.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("Do not place credentials in the OpenZero API URL.");
  }
  if (parsed.protocol === "http:" && !LOOPBACK_HOSTS.has(parsed.hostname.toLowerCase())) {
    throw new Error(
      "Plain HTTP is allowed only on loopback. Use HTTPS or an SSH tunnel to 127.0.0.1."
    );
  }
  if (parsed.search || parsed.hash) {
    throw new Error("OpenZero API URL cannot contain a query string or fragment.");
  }
  const cleanPath = parsed.pathname.replace(/\/+$/, "");
  if (cleanPath && cleanPath !== "/") {
    throw new Error("Use the OpenZero origin only, without an API route path.");
  }
  return parsed.origin;
}

export function normalizeBrowserAction(rawAction, currentUrl = "") {
  if (!rawAction || typeof rawAction !== "object" || Array.isArray(rawAction)) {
    throw new Error("OpenZero must return one JSON action object.");
  }
  const actionName = compactText(rawAction.action, 32).toLowerCase();
  if (!ACTION_SET.has(actionName)) {
    throw new Error(`Unsupported browser action: ${actionName || "missing"}.`);
  }

  const reason = compactText(rawAction.reason, 240);
  const normalized = { action: actionName, reason };

  if (actionName === "finish") {
    normalized.message = compactText(rawAction.message, 1600) || "Task finished.";
    return normalized;
  }

  if (actionName === "navigate") {
    const rawTarget = compactText(rawAction.url, 2000);
    if (!rawTarget || BLOCKED_SCHEMES_RE.test(rawTarget)) {
      throw new Error("Navigation requires an HTTP(S) URL.");
    }
    let target;
    try {
      target = new URL(rawTarget, currentUrl || undefined);
    } catch {
      throw new Error("Navigation URL is invalid.");
    }
    if (!["http:", "https:"].includes(target.protocol)) {
      throw new Error("Navigation is limited to HTTP(S) pages.");
    }
    normalized.url = target.href;
    return normalized;
  }

  if (["click", "type", "select"].includes(actionName)) {
    normalized.element_id = requireElementId(rawAction.element_id);
  }

  if (actionName === "type") {
    if (typeof rawAction.text !== "string") {
      throw new Error("Type actions require text.");
    }
    if (rawAction.text.length > 4000) {
      throw new Error("Type actions are limited to 4,000 characters.");
    }
    normalized.text = rawAction.text;
    normalized.clear = rawAction.clear !== false;
    return normalized;
  }

  if (actionName === "select") {
    normalized.value = compactText(rawAction.value, 500);
    if (!normalized.value) {
      throw new Error("Select actions require a value.");
    }
    return normalized;
  }

  if (actionName === "scroll") {
    const direction = compactText(rawAction.direction, 16).toLowerCase() || "down";
    if (!["up", "down", "top", "bottom"].includes(direction)) {
      throw new Error("Scroll direction must be up, down, top, or bottom.");
    }
    const requestedAmount = Number.parseInt(rawAction.amount, 10);
    normalized.direction = direction;
    normalized.amount = Number.isFinite(requestedAmount)
      ? Math.max(100, Math.min(requestedAmount, 2000))
      : 700;
    return normalized;
  }

  if (actionName === "wait") {
    const requestedMs = Number.parseInt(rawAction.ms, 10);
    normalized.ms = Number.isFinite(requestedMs)
      ? Math.max(100, Math.min(requestedMs, 5000))
      : 750;
    return normalized;
  }

  return normalized;
}

function findElement(snapshot, elementId) {
  const interactive = Array.isArray(snapshot?.interactive) ? snapshot.interactive : [];
  return interactive.find((element) => element?.id === elementId) || null;
}

export function actionPreview(action, snapshot = null) {
  const element = action?.element_id ? findElement(snapshot, action.element_id) : null;
  const label = compactText(element?.label || element?.text || action?.element_id, 100);
  switch (action?.action) {
    case "navigate":
      return `Navigate to ${action.url}`;
    case "click":
      return `Click ${label || action.element_id}`;
    case "type":
      return `Type ${String(action.text || "").length} character(s) into ${label || action.element_id}`;
    case "select":
      return `Choose an option in ${label || action.element_id}`;
    case "scroll":
      return `Scroll ${action.direction}`;
    case "wait":
      return `Wait ${action.ms} ms`;
    case "back":
      return "Go back";
    case "forward":
      return "Go forward";
    case "finish":
      return compactText(action.message, 160);
    default:
      return compactText(action?.action, 80) || "Unknown action";
  }
}

export function classifyBrowserAction(action, snapshot, settings = DEFAULT_SETTINGS) {
  const result = {
    allowed: true,
    needsApproval: false,
    needsSiteConsent: false,
    destinationUrl: "",
    reason: ""
  };

  if (action.action === "finish" || action.action === "wait" || action.action === "scroll") {
    return result;
  }

  if (["navigate", "back", "forward"].includes(action.action) && !settings.allowNavigation) {
    return { ...result, allowed: false, reason: "Navigation is disabled in extension settings." };
  }
  if (action.action === "click" && !settings.allowClicking) {
    return { ...result, allowed: false, reason: "Clicking is disabled in extension settings." };
  }
  if (["type", "select"].includes(action.action) && !settings.allowTyping) {
    return { ...result, allowed: false, reason: "Typing and selection are disabled in extension settings." };
  }

  if (action.action === "navigate" && !sameOrigin(snapshot?.url, action.url)) {
    result.needsSiteConsent = true;
    result.destinationUrl = action.url;
  }

  if (["click", "type", "select"].includes(action.action)) {
    const element = findElement(snapshot, action.element_id);
    if (!element) {
      return {
        ...result,
        allowed: false,
        reason: "The target is not in the current inspected element set."
      };
    }

    if (["password", "payment", "secret", "file", "captcha"].includes(element.sensitive_kind)) {
      return {
        ...result,
        allowed: false,
        reason: `OpenZero Tab Pilot blocks ${element.sensitive_kind} fields.`
      };
    }

    if (
      settings.requireRiskApproval &&
      (element.risk === "consequential" ||
        RISKY_LABEL_RE.test(`${element.label || ""} ${element.text || ""}`))
    ) {
      result.needsApproval = true;
    }

    if (
      settings.requireRiskApproval &&
      ["type", "select"].includes(action.action) &&
      element.sensitive_kind === "personal"
    ) {
      result.needsApproval = true;
    }

    if (
      action.action === "click" &&
      element.href &&
      isHttpPage(element.href) &&
      !sameOrigin(snapshot?.url, element.href)
    ) {
      result.needsSiteConsent = true;
      result.destinationUrl = element.href;
    }
  }

  return result;
}

export function mergeSettings(saved = {}) {
  const merged = { ...DEFAULT_SETTINGS, ...(saved || {}) };
  merged.maxSteps = Math.max(1, Math.min(Number.parseInt(merged.maxSteps, 10) || 12, 30));
  merged.requestTimeoutSeconds = Math.max(
    15,
    Math.min(Number.parseInt(merged.requestTimeoutSeconds, 10) || 120, 300)
  );
  merged.apiBaseUrl = String(merged.apiBaseUrl || DEFAULT_SETTINGS.apiBaseUrl);
  merged.apiKey = String(merged.apiKey || "");
  merged.model = compactText(merged.model, 200) || DEFAULT_SETTINGS.model;
  merged.openzeroSpark = ["off", "auto", "force"].includes(merged.openzeroSpark)
    ? merged.openzeroSpark
    : "auto";
  return merged;
}

export function mergeEffectiveSettings(saved = {}, managed = {}) {
  const allowedManaged = {};
  for (const key of ["apiBaseUrl", "apiKey", "model"]) {
    if (typeof managed?.[key] === "string" && managed[key].trim()) {
      allowedManaged[key] = managed[key].trim();
    }
  }
  return mergeSettings({ ...(saved || {}), ...allowedManaged });
}
