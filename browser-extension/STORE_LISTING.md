# OpenZero Tab Pilot - Chrome Web Store listing

## Product details

- Name: OpenZero Tab Pilot
- Summary: Grant one browser tab to your self-hosted OpenZero node for visible, consent-controlled browser work.
- Category: Productivity
- Language: English (United Kingdom)
- Homepage: https://openzero.talktoai.org/tab-pilot
- Support: https://github.com/ResearchForumOnline/OpenZero/issues
- Privacy policy: https://openzero.talktoai.org/tab-pilot-privacy

## Detailed description

OpenZero Tab Pilot connects one explicitly approved Brave or Chromium tab to a
self-hosted OpenZero node.

You choose the tab, grant it, describe a task, and watch each step. The
extension inspects a bounded, privacy-reduced view of the page and asks your
configured OpenZero node for one structured action at a time.

Tab Pilot can navigate, click inspected controls, type into ordinary fields,
choose options, scroll, wait, go back, and go forward. New sites pause for the
browser's own permission prompt. Consequential clicks and personal-data entry
pause for one-time human approval.

Safety boundaries:

- one explicitly granted tab at a time;
- no analytics, advertising, or third-party trackers;
- no cookie or browser-history access;
- no password, payment-card, secret, token, one-time-code, CAPTCHA, or file
  upload entry;
- no arbitrary JavaScript or model-generated selectors;
- visible stop and revoke controls;
- session grants clear when the browser or extension restarts.

OpenZero is self-hosted. For a remote node, connect through HTTPS, a private VPN,
or an SSH tunnel to loopback. The extension refuses plain remote HTTP.

## Single purpose

Allow a person to explicitly grant one normal browser tab to their self-hosted
OpenZero node for visible, bounded, policy-controlled browser work.

## Permission justifications

- `activeTab`: grants temporary access only after the user clicks the extension
  for the current tab.
- `scripting`: injects the fixed, bundled inspector/controller into the granted
  tab. It never executes remote or model-generated code.
- `storage`: stores connection and safety settings locally and keeps grants and
  run state in session storage.
- `tabs`: reads the granted tab's URL/title and observes navigation so the
  extension can stop or pause when the tab or origin changes.
- Optional `http://*/*` and `https://*/*`: requested at runtime only for the
  exact OpenZero API origin and sites the user explicitly grants. No install-time
  host access is requested.

## Data-use disclosure

Handled only to provide the user-facing feature:

- user-written task instructions;
- website URL and page title;
- bounded visible page text;
- bounded headings and interactive-control labels;
- recent action-result summaries;
- extension settings and the configured OpenZero API token.

The extension does not sell data, use data for advertising or credit decisions,
or transfer data to unrelated third parties. It sends task and page context only
to the exact OpenZero API origin configured by the user. It does not intentionally
collect cookies, browsing history, screenshots, values from inputs or textareas,
passwords, payment details, authentication information, secrets, one-time codes,
or file contents.

## Reviewer test instructions

1. Install the extension and open Extension options.
2. Set an OpenZero API origin with a valid planner-only token. A loopback
   OpenZero node at `http://127.0.0.1:1024` is recommended.
3. Confirm the configured model appears when selecting
   "Test connection & list models".
4. Open a normal non-sensitive HTTP(S) test page.
5. Open the extension, select "Grant this tab", enter a read-only task such as
   "Find the support link and tell me its label. Do not submit anything.", and
   select "Start controlled work".
6. Observe the persistent in-page status card and use "Stop & revoke".

If reviewer credentials are requested by the dashboard, create a short-lived
planner-only token for the dedicated review node; never upload an administrator
key.
