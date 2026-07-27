import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(root, "manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

assert.equal(manifest.manifest_version, 3, "Manifest must be V3.");
assert.equal(manifest.background?.type, "module", "Service worker must be an ES module.");
assert.ok(manifest.permissions.includes("activeTab"), "activeTab is required.");
assert.ok(manifest.permissions.includes("scripting"), "scripting is required.");
assert.ok(!manifest.permissions.includes("debugger"), "debugger permission is forbidden.");
assert.ok(!manifest.permissions.includes("cookies"), "cookies permission is forbidden.");
assert.ok(!manifest.permissions.includes("webRequest"), "webRequest permission is forbidden.");
assert.ok(!manifest.permissions.includes("nativeMessaging"), "nativeMessaging is forbidden.");
assert.ok(
  !Array.isArray(manifest.host_permissions) || manifest.host_permissions.length === 0,
  "Install-time host_permissions must remain empty."
);
assert.deepEqual(
  [...manifest.optional_host_permissions].sort(),
  ["http://*/*", "https://*/*"],
  "Only optional HTTP(S) origin templates are allowed."
);

const referencedFiles = [
  manifest.background.service_worker,
  manifest.action.default_popup,
  manifest.options_page,
  "src/content.js",
  "src/popup.js",
  "src/popup.css",
  "src/options.js",
  "src/options.css",
  "src/shared/policy.js",
  "src/shared/openzero-client.js"
];

for (const relative of referencedFiles) {
  const target = path.join(root, relative);
  assert.ok((await stat(target)).isFile(), `Referenced file missing: ${relative}`);
}

for (const htmlFile of [manifest.action.default_popup, manifest.options_page]) {
  const html = await readFile(path.join(root, htmlFile), "utf8");
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), `${htmlFile} contains inline script.`);
  assert.ok(!/\son\w+\s*=/i.test(html), `${htmlFile} contains an inline event handler.`);
}

for (const jsFile of referencedFiles.filter((file) => file.endsWith(".js"))) {
  const source = await readFile(path.join(root, jsFile), "utf8");
  assert.ok(!/\beval\s*\(/.test(source), `${jsFile} uses eval.`);
  assert.ok(!/\bnew\s+Function\s*\(/.test(source), `${jsFile} uses new Function.`);
  assert.ok(!/ztapi_[A-Za-z0-9_-]{12,}|oz_[A-Za-z0-9_-]{20,}/.test(source), `${jsFile} contains a key-like token.`);
}

console.log("Manifest V3 and static security validation passed.");
