import { listOpenZeroModels } from "./shared/openzero-client.js";
import {
  mergeEffectiveSettings,
  mergeSettings,
  normalizeApiBaseUrl,
  originPattern
} from "./shared/policy.js";

const SETTINGS_KEY = "settings";
const form = document.querySelector("#settings-form");
const fields = {
  apiUrl: document.querySelector("#api-url"),
  apiKey: document.querySelector("#api-key"),
  clearKey: document.querySelector("#clear-key"),
  model: document.querySelector("#model"),
  spark: document.querySelector("#spark"),
  maxSteps: document.querySelector("#max-steps"),
  timeout: document.querySelector("#timeout"),
  allowNavigation: document.querySelector("#allow-navigation"),
  allowClicking: document.querySelector("#allow-clicking"),
  allowTyping: document.querySelector("#allow-typing"),
  riskApproval: document.querySelector("#risk-approval"),
  test: document.querySelector("#test"),
  testResult: document.querySelector("#test-result"),
  save: document.querySelector("#save"),
  saveResult: document.querySelector("#save-result")
};

let savedSettings = mergeSettings();
let savedLocalSettings = {};
let managedSettings = {};

function settingsFromForm() {
  return mergeSettings({
    ...savedSettings,
    apiBaseUrl: normalizeApiBaseUrl(fields.apiUrl.value),
    apiKey: fields.clearKey.checked
      ? ""
      : fields.apiKey.value.trim() || savedSettings.apiKey,
    model: fields.model.value.trim(),
    openzeroSpark: fields.spark.value,
    maxSteps: Number.parseInt(fields.maxSteps.value, 10),
    requestTimeoutSeconds: Number.parseInt(fields.timeout.value, 10),
    allowNavigation: fields.allowNavigation.checked,
    allowClicking: fields.allowClicking.checked,
    allowTyping: fields.allowTyping.checked,
    requireRiskApproval: fields.riskApproval.checked
  });
}

function render(settings) {
  fields.apiUrl.value = settings.apiBaseUrl;
  fields.apiKey.value = "";
  fields.apiKey.placeholder = settings.apiKey
    ? "Key saved — leave blank to keep it"
    : "Paste the one-time OpenZero API key";
  fields.clearKey.checked = false;
  fields.model.value = settings.model;
  fields.spark.value = settings.openzeroSpark;
  fields.maxSteps.value = settings.maxSteps;
  fields.timeout.value = settings.requestTimeoutSeconds;
  fields.allowNavigation.checked = settings.allowNavigation;
  fields.allowClicking.checked = settings.allowClicking;
  fields.allowTyping.checked = settings.allowTyping;
  fields.riskApproval.checked = settings.requireRiskApproval;
}

function requestApiOrigin(settings) {
  const pattern = originPattern(settings.apiBaseUrl);
  return chrome.permissions.request({ origins: [pattern] });
}

async function load() {
  const [stored, managed] = await Promise.all([
    chrome.storage.local.get(SETTINGS_KEY),
    chrome.storage.managed.get().catch(() => ({}))
  ]);
  savedLocalSettings = stored[SETTINGS_KEY] || {};
  managedSettings = managed || {};
  savedSettings = mergeEffectiveSettings(savedLocalSettings, managedSettings);
  render(savedSettings);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  fields.save.disabled = true;
  fields.saveResult.textContent = "";
  try {
    const next = settingsFromForm();
    if (!next.model) {
      throw new Error("A model name is required.");
    }
    const allowed = await requestApiOrigin(next);
    if (!allowed) {
      throw new Error("Brave did not grant access to the OpenZero API origin.");
    }
    const localSettings = { ...next };
    for (const key of ["apiBaseUrl", "apiKey", "model"]) {
      if (typeof managedSettings[key] === "string" && managedSettings[key].trim()) {
        delete localSettings[key];
      }
    }
    await chrome.storage.local.set({ [SETTINGS_KEY]: localSettings });
    savedLocalSettings = localSettings;
    savedSettings = mergeEffectiveSettings(savedLocalSettings, managedSettings);
    render(savedSettings);
    fields.saveResult.textContent = "Saved.";
  } catch (error) {
    fields.saveResult.textContent = `Not saved: ${error.message}`;
  } finally {
    fields.save.disabled = false;
  }
});

fields.test.addEventListener("click", async () => {
  fields.test.disabled = true;
  fields.testResult.textContent = "Testing…";
  try {
    const settings = settingsFromForm();
    const allowed = await requestApiOrigin(settings);
    if (!allowed) {
      throw new Error("Brave did not grant access to the OpenZero API origin.");
    }
    const models = await listOpenZeroModels(settings);
    if (!models.includes(settings.model)) {
      throw new Error(
        `Connected, but configured model ${settings.model} is not installed. ` +
          `Available: ${models.join(", ") || "none"}`
      );
    }
    fields.testResult.textContent =
      `Connected. Configured model is available: ${settings.model}\n\n` +
      `Installed models:\n${models.map((model) => `- ${model}`).join("\n")}`;
  } catch (error) {
    fields.testResult.textContent = `Connection failed:\n${error.message}`;
  } finally {
    fields.test.disabled = false;
  }
});

fields.clearKey.addEventListener("change", () => {
  fields.apiKey.disabled = fields.clearKey.checked;
});

load().catch((error) => {
  fields.saveResult.textContent = `Could not load settings: ${error.message}`;
});
