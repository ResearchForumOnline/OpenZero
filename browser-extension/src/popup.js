const elements = {
  dot: document.querySelector("#status-dot"),
  headline: document.querySelector("#headline"),
  pageTitle: document.querySelector("#page-title"),
  pageOrigin: document.querySelector("#page-origin"),
  grantBadge: document.querySelector("#grant-badge"),
  grant: document.querySelector("#grant"),
  revoke: document.querySelector("#revoke"),
  forgetSite: document.querySelector("#forget-site"),
  pendingSite: document.querySelector("#pending-site"),
  pendingSiteText: document.querySelector("#pending-site-text"),
  allowSite: document.querySelector("#allow-site"),
  pendingRisk: document.querySelector("#pending-risk"),
  pendingRiskText: document.querySelector("#pending-risk-text"),
  task: document.querySelector("#task"),
  start: document.querySelector("#start"),
  stop: document.querySelector("#stop"),
  stepBadge: document.querySelector("#step-badge"),
  runMessage: document.querySelector("#run-message"),
  apiState: document.querySelector("#api-state"),
  notice: document.querySelector("#notice"),
  refresh: document.querySelector("#refresh"),
  options: document.querySelector("#options")
};

let currentStatus = null;
let refreshTimer = null;

function setHidden(element, hidden) {
  element.classList.toggle("hidden", hidden);
}

function showNotice(message) {
  elements.notice.textContent = String(message || "Unknown error");
  setHidden(elements.notice, false);
}

function clearNotice() {
  elements.notice.textContent = "";
  setHidden(elements.notice, true);
}

async function send(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) {
    throw new Error(response?.error || response?.message || "OpenZero Tab Pilot command failed.");
  }
  return response;
}

function runTone(run) {
  if (!run) {
    return currentStatus?.granted ? "granted" : "off";
  }
  if (run.status === "running") {
    return "running";
  }
  if (run.status === "completed") {
    return "done";
  }
  if (run.status === "error") {
    return "error";
  }
  return "paused";
}

function render(status) {
  currentStatus = status;
  const { tab, granted, run, pending, api } = status;
  const tone = runTone(run);
  elements.dot.className = `status-dot ${tone}`;
  elements.headline.textContent =
    tone === "running"
      ? "OpenZero is working visibly"
      : granted
        ? "Tab access is active"
        : "No tab access";
  elements.pageTitle.textContent = tab.title || "Untitled page";
  elements.pageOrigin.textContent = tab.origin || tab.url || "Unsupported Brave page";
  elements.grantBadge.textContent = granted ? "Granted" : "Not granted";
  elements.grantBadge.className = `badge ${granted ? "good" : "neutral"}`;

  setHidden(elements.grant, granted || !tab.supported);
  elements.grant.disabled = !tab.supported;
  setHidden(elements.revoke, !granted);
  setHidden(elements.forgetSite, !status.sitePermission || !tab.supported);

  const activelyRunning = run?.status === "running";
  setHidden(elements.stop, !activelyRunning);
  elements.start.disabled = !granted || !api.configured || activelyRunning || Boolean(pending);
  elements.task.disabled = activelyRunning;
  if (run?.task && !elements.task.value) {
    elements.task.value = run.task;
  }
  elements.stepBadge.textContent = run
    ? `${run.status} · ${run.step}/${run.maxSteps}`
    : "Idle";
  elements.stepBadge.className = `badge ${
    activelyRunning ? "good" : pending || run?.status === "error" ? "warn" : "neutral"
  }`;
  elements.runMessage.textContent =
    run?.message ||
    (granted
      ? "Ready. OpenZero will inspect before every action."
      : "Grant this tab before starting.");

  setHidden(elements.pendingSite, pending?.kind !== "site");
  setHidden(elements.pendingRisk, pending?.kind !== "risk");
  if (pending?.kind === "site") {
    elements.pendingSiteText.textContent = `OpenZero wants to continue at ${pending.destinationOrigin}. Proposed step: ${pending.preview}`;
    elements.allowSite.dataset.pattern = pending.pattern;
  }
  if (pending?.kind === "risk") {
    elements.pendingRiskText.textContent = pending.preview;
  }

  elements.apiState.textContent = api.configured
    ? `OpenZero: ${api.model} at ${api.baseUrl}`
    : "OpenZero connection is not configured. Open settings before starting.";
}

async function refresh({ quiet = false } = {}) {
  if (!quiet) {
    clearNotice();
  }
  try {
    const status = await send({ type: "GET_STATUS" });
    render(status);
  } catch (error) {
    if (!quiet) {
      showNotice(error.message);
    }
  }
}

async function act(button, operation) {
  clearNotice();
  button.disabled = true;
  try {
    await operation();
  } catch (error) {
    showNotice(error.message);
  } finally {
    button.disabled = false;
    await refresh({ quiet: true });
  }
}

elements.grant.addEventListener("click", () =>
  act(elements.grant, () => send({ type: "GRANT_ACTIVE_TAB" }))
);

elements.revoke.addEventListener("click", () =>
  act(elements.revoke, () => send({ type: "REVOKE_ACTIVE_TAB" }))
);

elements.stop.addEventListener("click", () =>
  act(elements.stop, () => send({ type: "STOP_ACTIVE_RUN" }))
);

elements.start.addEventListener("click", () =>
  act(elements.start, async () => {
    const task = elements.task.value.trim();
    if (!task) {
      throw new Error("Describe the browser task first.");
    }
    elements.runMessage.textContent = "OpenZero is starting…";
    await send({ type: "START_TASK", task });
  })
);

elements.allowSite.addEventListener("click", () =>
  act(elements.allowSite, async () => {
    const pattern = elements.allowSite.dataset.pattern;
    if (!pattern) {
      throw new Error("The pending destination is missing.");
    }
    const granted = await chrome.permissions.request({ origins: [pattern] });
    if (!granted) {
      throw new Error("Brave did not grant access to that destination.");
    }
    await send({ type: "APPROVE_SITE", pattern });
  })
);

elements.approveRisk = document.querySelector("#approve-risk");
elements.approveRisk.addEventListener("click", () =>
  act(elements.approveRisk, () => send({ type: "APPROVE_RISK" }))
);

document.querySelectorAll(".deny-pending").forEach((button) => {
  button.addEventListener("click", () =>
    act(button, () => send({ type: "DENY_PENDING" }))
  );
});

elements.forgetSite.addEventListener("click", () =>
  act(elements.forgetSite, async () => {
    const pattern = currentStatus?.pagePattern;
    if (!pattern) {
      throw new Error("The current site origin is unavailable.");
    }
    await send({ type: "REVOKE_SITE", pattern });
  })
);

elements.refresh.addEventListener("click", () => refresh());
elements.options.addEventListener("click", () => chrome.runtime.openOptionsPage());

window.addEventListener("unload", () => clearInterval(refreshTimer));

refresh();
refreshTimer = setInterval(() => refresh({ quiet: true }), 1000);
