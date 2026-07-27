import test from "node:test";
import assert from "node:assert/strict";
import {
  classifyBrowserAction,
  mergeEffectiveSettings,
  normalizeApiBaseUrl,
  normalizeBrowserAction,
  originPattern,
  sameOrigin
} from "../src/shared/policy.js";

test("managed connection settings override local values without weakening safety settings", () => {
  const settings = mergeEffectiveSettings(
    {
      apiBaseUrl: "http://localhost:1024",
      apiKey: "local-key",
      model: "other:latest",
      requireRiskApproval: false
    },
    {
      apiBaseUrl: "http://127.0.0.1:1024",
      apiKey: "managed-key",
      model: "openzerogemma:latest",
      requireRiskApproval: false
    }
  );
  assert.equal(settings.apiBaseUrl, "http://127.0.0.1:1024");
  assert.equal(settings.apiKey, "managed-key");
  assert.equal(settings.model, "openzerogemma:latest");
  assert.equal(settings.requireRiskApproval, false);
});

const settings = {
  allowNavigation: true,
  allowClicking: true,
  allowTyping: true,
  requireRiskApproval: true
};

function snapshot(element = {}) {
  return {
    snapshot_id: "snapshot-1",
    url: "https://example.com/account",
    interactive: [
      {
        id: "e1",
        label: "Open help",
        text: "",
        href: "",
        risk: "",
        sensitive_kind: "",
        ...element
      }
    ]
  };
}

test("API URL accepts loopback HTTP and canonicalizes trailing slash", () => {
  assert.equal(normalizeApiBaseUrl("http://127.0.0.1:1024/"), "http://127.0.0.1:1024");
  assert.equal(normalizeApiBaseUrl("http://localhost:1024"), "http://localhost:1024");
});

test("API URL rejects remote plain HTTP and embedded credentials", () => {
  assert.throws(() => normalizeApiBaseUrl("http://192.0.2.10:1024"), /loopback/i);
  assert.throws(() => normalizeApiBaseUrl("https://user:pass@example.com"), /credentials/i);
});

test("API URL accepts remote HTTPS origin only", () => {
  assert.equal(normalizeApiBaseUrl("https://openzero.example"), "https://openzero.example");
  assert.throws(() => normalizeApiBaseUrl("https://openzero.example/v1"), /origin only/i);
});

test("origin helpers preserve ports and compare exact origins", () => {
  assert.equal(originPattern("http://127.0.0.1:1024/a"), "http://127.0.0.1:1024/*");
  assert.equal(sameOrigin("https://example.com/a", "https://example.com/b"), true);
  assert.equal(sameOrigin("https://example.com", "https://other.example"), false);
});

test("normal click is allowed", () => {
  const action = normalizeBrowserAction({ action: "click", element_id: "e1" });
  assert.deepEqual(classifyBrowserAction(action, snapshot(), settings), {
    allowed: true,
    needsApproval: false,
    needsSiteConsent: false,
    destinationUrl: "",
    reason: ""
  });
});

test("consequential click needs one-time approval", () => {
  const action = normalizeBrowserAction({ action: "click", element_id: "e1" });
  const decision = classifyBrowserAction(
    action,
    snapshot({ label: "Submit application", risk: "consequential" }),
    settings
  );
  assert.equal(decision.allowed, true);
  assert.equal(decision.needsApproval, true);
});

test("password and payment fields are denied", () => {
  const action = normalizeBrowserAction({
    action: "type",
    element_id: "e1",
    text: "not-a-real-secret"
  });
  assert.match(
    classifyBrowserAction(action, snapshot({ sensitive_kind: "password" }), settings).reason,
    /blocks password/i
  );
  assert.match(
    classifyBrowserAction(action, snapshot({ sensitive_kind: "payment" }), settings).reason,
    /blocks payment/i
  );
  assert.match(
    classifyBrowserAction(action, snapshot({ sensitive_kind: "captcha" }), settings).reason,
    /blocks captcha/i
  );
});

test("personal-data typing needs approval", () => {
  const action = normalizeBrowserAction({
    action: "type",
    element_id: "e1",
    text: "user@example.test"
  });
  const decision = classifyBrowserAction(
    action,
    snapshot({ sensitive_kind: "personal" }),
    settings
  );
  assert.equal(decision.needsApproval, true);
});

test("cross-origin navigation needs site consent", () => {
  const action = normalizeBrowserAction(
    { action: "navigate", url: "https://support.example.net/help" },
    "https://example.com/account"
  );
  const decision = classifyBrowserAction(action, snapshot(), settings);
  assert.equal(decision.allowed, true);
  assert.equal(decision.needsSiteConsent, true);
  assert.equal(decision.destinationUrl, "https://support.example.net/help");
});

test("cross-origin inspected links need site consent before click", () => {
  const action = normalizeBrowserAction({ action: "click", element_id: "e1" });
  const decision = classifyBrowserAction(
    action,
    snapshot({ href: "https://support.example.net/help" }),
    settings
  );
  assert.equal(decision.needsSiteConsent, true);
});

test("unsupported schemes and invented selectors are rejected", () => {
  assert.throws(
    () =>
      normalizeBrowserAction(
        { action: "navigate", url: "javascript:alert(1)" },
        "https://example.com"
      ),
    /HTTP\(S\)/i
  );
  assert.throws(
    () => normalizeBrowserAction({ action: "click", element_id: "#submit" }),
    /element_id/i
  );
});

test("scroll and wait values are bounded", () => {
  assert.equal(normalizeBrowserAction({ action: "scroll", amount: 99999 }).amount, 2000);
  assert.equal(normalizeBrowserAction({ action: "wait", ms: 99999 }).ms, 5000);
});
