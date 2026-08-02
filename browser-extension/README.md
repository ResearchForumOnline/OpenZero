# OpenZero Tab Pilot for Brave

OpenZero Tab Pilot is a signed Chromium Manifest V3 extension that lets a
person explicitly grant **one normal Brave tab** to OpenZero for visible,
step-by-step browser work.

The public extension is published in the Chrome Web Store. Linux OpenZero
installs and updates can continue to configure the self-hosted signed build
through Brave managed policy; a verified ZIP and guided Windows setup helper
remain available for offline and source-verifiable installs.

## What it can do

- inspect a bounded, privacy-reduced text/element snapshot of the granted tab;
- ask OpenZero for one strict JSON action at a time through the dedicated
  authenticated `POST /v1/browser/plan` API;
- navigate, click an inspected element, type into ordinary fields, choose a
  select option, scroll, wait, go back, and go forward;
- show a persistent in-page status card plus a Brave toolbar badge while access
  is active;
- stop immediately from the popup or the on-page **STOP AND REVOKE TAB** button;
- pause before a new origin and use Brave's own optional-origin permission
  prompt;
- pause before final/consequential clicks and personal-data entry;
- revoke a tab grant independently from saved per-origin access.

## What it deliberately cannot do

- operate on `brave://`, `chrome://`, extension, file, data, or other privileged
  pages;
- inject arbitrary JavaScript or accept model-generated CSS selectors;
- type into password, payment-card, secret/token, one-time-code, or file-upload
  fields;
- solve CAPTCHAs;
- silently cross into a new site;
- silently send, buy, post, publish, submit, delete, sign in, transfer, install,
  upload, or perform a similarly consequential click;
- read input values; page snapshots expose only `has_value`, never the value;
- keep an unattended grant after a browser restart.

## Compatibility with the current OpenZero code

The inspected OpenZero source exposes:

- authenticated `GET /v1/models`;
- authenticated `POST /v1/browser/plan`;
- Moltbot on loopback for a separate, headless Chrome instance.

Moltbot does not control the user's existing Brave tabs. This extension uses
model discovery plus the strict planner route and keeps all tab authority inside
Brave. The browser-planner token cannot call general chat completions.

The default model name is `openzerogemma:latest`. It must be installed and returned by
`/v1/models`; otherwise select any installed OpenZero model in the options page.

## Install in Brave

### Chrome Web Store: recommended interactive install

Install the public listing in Brave, Chrome, or another compatible Chromium
browser:

https://chromewebstore.google.com/detail/openzero-tab-pilot/cgaalobjjknalamgchppccbocnhonhbf

The Chrome Web Store extension ID is `cgaalobjjknalamgchppccbocnhonhbf`.
Open the extension options after installation and connect it to your OpenZero
node. Remote nodes should remain loopback-bound and be reached through the SSH
tunnel described on https://openzero.talktoai.org/tab-pilot.

### Linux: automatic managed install

The normal OpenZero installer and updater detect Brave and run:

```bash
./install-tab-pilot.sh
```

That helper verifies the hosted update endpoints, rotates a scoped Tab Pilot
token through loopback, writes `/etc/brave/policies/managed/openzero-tab-pilot.json`,
and lets Brave install/update extension ID
`bjjhckhjkjodankbndllgloanjnfmlmo`. Use `--no-tab-pilot` on the main installer
or updater to opt out.

### Windows: verified unpacked install

1. Keep this folder somewhere only your Windows account can modify.
2. Open `brave://extensions`.
3. Turn on **Developer mode**.
4. Choose **Load unpacked**.
5. Select this `openzero-brave-extension` folder.
6. Open the extension's **Details** page and pin it if desired.
7. Open **Extension options** and configure the OpenZero API.

No build step and no `npm install` are required.

For the deterministic ZIP handoff, extract
`dist/OpenZero-Tab-Pilot-Brave-v0.2.0.zip` first, then select the extracted
folder in **Load unpacked**. Brave cannot load the ZIP directly.

## Connect to OpenZero safely

The safest default is a loopback API:

```text
http://127.0.0.1:1024
```

If OpenZero runs on another server, do not send its bearer key over plain remote
HTTP. Use HTTPS with a valid certificate, a private VPN, or an SSH tunnel. A
typical tunnel shape is:

```bash
ssh -N -L 1024:127.0.0.1:1024 your-user@your-openzero-server
```

Then keep the extension API origin set to `http://127.0.0.1:1024`.

Managed Linux installs use a separate browser-planner-only token delivered
through Brave managed storage. Manual installs can still use an OpenZero API key
created from a direct local administrator session. Tokens are never injected
into page JavaScript or shown in the popup, and are sent only as bearer headers
to the exact approved API origin.

## Use

1. Open a normal `http://` or `https://` page.
2. Click the extension and choose **Grant this tab**.
3. Describe a bounded task. State any important limits explicitly.
4. Choose **Start controlled work**.
5. Watch the in-page status card and toolbar badge.
6. If the task reaches a new origin, review and approve that exact destination.
7. If a consequential action appears, review and approve that exact action once
   or deny it and let OpenZero plan another route.
8. Use **Stop & revoke** when finished.

A persistent site permission does not grant tabs automatically. Every tab still
requires the user to open the popup and grant that exact tab.

## Safety design

The extension treats the page and model as untrusted inputs:

1. user gesture grants a single tab;
2. a bounded snapshot creates ephemeral element IDs such as `e3`;
3. OpenZero returns exactly one schema-checked JSON action;
4. local policy checks settings, element class, origin, and risk;
5. the content controller checks the same grant and snapshot again;
6. the page is re-inspected before the next model action.

The extension stops on stale element snapshots, unexpected cross-site
navigation, unsupported schemes, policy violations it cannot replan around,
model/API errors, request timeout, user stop, or the configured step limit.

See:

- [Architecture](docs/ARCHITECTURE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [OpenZero API integration](docs/OPENZERO_API_INTEGRATION.md)
- [Privacy](PRIVACY.md)
- [Security reporting and review notes](SECURITY.md)

## Development and verification

The source has no runtime npm dependencies. Node.js 20 or newer is used only for
tests and static validation:

```powershell
npm run check
npm run package
```

The check validates the manifest and extension source references, rejects
dangerous permissions and inline/eval-like script patterns, and runs unit tests
for URL, origin, action, risk, sensitive-field, prompt, parser, and OpenZero API
behavior.

For a real browser smoke test, load the unpacked folder in Brave and use a
non-sensitive local test page. Do not test final submissions, purchases,
messages, account changes, or production data.

## Known limitations

- Some complex apps hide controls inside closed shadow roots, canvases, remote
  frames, or virtualized lists; those controls may not be inspectable.
- Cross-origin iframes are intentionally not controlled.
- Service workers can be interrupted by browser updates or extension reloads.
  Session state fails closed after restart.
- A model can choose a poor action. Local checks reduce authority; they do not
  make model output inherently trustworthy.
- The current risk classifier is intentionally conservative and may ask for
  approval more often than necessary.
- Browser-store publication, localization, accessibility audit, and broader
  end-to-end Brave automation remain release work.

## Project status

Version `0.2.0` is self-hosted as a signed CRX with managed Linux installation
and updates. Windows unpacked installation still requires deliberate Brave
approval.
