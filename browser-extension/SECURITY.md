# Security

## Intended boundary

OpenZero Tab Pilot is an operator-controlled extension. It assumes the browser
profile owner is physically present to grant a tab, approve a new site, and
approve a consequential action.

Do not install it in a shared browser profile. Do not distribute a folder
containing a saved API key. Do not expose the OpenZero operator API directly to
the public internet.

## Review before release

Before any store or production release:

1. perform a manual Manifest V3 permission and CSP review;
2. test tab-grant revocation across same-origin and cross-origin navigation;
3. test prompt-injection pages and misleading button labels;
4. test framework-controlled inputs without weakening sensitive-field blocks;
5. audit all status/error paths for credential leakage;
6. test Brave stable on Windows and Linux;
7. add a signed release process and reproducible package hash;
8. run an independent security review.

## Reporting

Keep reports private until fixed. Include the extension version, Brave version,
reproduction steps, expected/actual result, and whether a real origin, account,
or OpenZero key was exposed. Never attach live credentials or private page
content.

## Non-goals

This prototype does not claim to defeat a compromised browser, malicious
extension with stronger permissions, host malware, or an attacker who already
controls the OpenZero API key.
