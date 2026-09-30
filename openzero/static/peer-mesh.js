/* Direct notes between independently owned OpenZero nodes. No automatic sync. */
(() => {
  'use strict';
  const box = document.getElementById('peer-mesh-panel');
  if (!box) return;
  const element = id => document.getElementById(id);
  const notice = text => { element('peer-notice').textContent = text; };
  async function call(path, data) {
    const headers = {};
    const ownerToken = element('workbench-token')?.value.trim();
    if (ownerToken) headers.Authorization = 'Bearer ' + ownerToken;
    const response = await fetch('/api/peers/' + path, data === undefined
      ? { credentials: 'same-origin', cache: 'no-store', headers }
      : { method: 'POST', credentials: 'same-origin', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Peer operation failed.');
    return result;
  }
  function button(label, action) {
    const item = document.createElement('button');
    item.type = 'button'; item.className = 'action-btn'; item.textContent = label;
    item.addEventListener('click', () => run(action));
    return item;
  }
  function renderNotes(parent, notes, inbox) {
    parent.replaceChildren();
    for (const note of [...notes].reverse()) {
      const details = document.createElement('details');
      const heading = document.createElement('summary');
      heading.textContent = note.content.title || 'Untitled note';
      const text = document.createElement('pre');
      text.style.whiteSpace = 'pre-wrap'; text.style.overflowWrap = 'anywhere';
      text.textContent = note.content.text;
      const digest = document.createElement('div'); digest.className = 'hint';
      digest.textContent = note.id + (inbox ? ' · Untrusted text for your review. Never executed or relayed.' : ' · Available to authenticated peers when enabled.');
      details.append(heading, text, digest);
      if (!inbox) details.append(button('Exchange this exact note with all my peers', async () => {
        const result = await call('sync', { consent: true, note_ids: [note.id] });
        notice(JSON.stringify(result));
      }));
      details.append(button('Remove this note', async () => {
        await call(inbox ? 'inbox/delete' : 'delete', { id: note.id });
        notice('Note removed locally. Copies already received by another owner cannot be recalled.');
      }));
      parent.append(details);
    }
  }
  async function refresh() {
    const status = await call('status');
    element('peer-enabled').checked = status.enabled;
    element('peer-summary').textContent = (status.enabled ? 'Direct exchange enabled' : 'Local only — peer exchange disabled')
      + ' · ' + status.peers.length + ' trusted peers · ' + status.published_count + ' published notes · ' + status.inbox_count + ' received notes';
    const list = element('peer-list'); list.replaceChildren();
    for (const peer of status.peers) {
      const row = document.createElement('div'); row.className = 'hint';
      const text = document.createElement('span'); text.textContent = peer.label + ' — ' + peer.origin + ' ';
      row.append(text, button('Exchange latest batch with this peer', async () => {
        const result = await call('sync', { consent: true, peer_ids: [peer.id] });
        notice(JSON.stringify(result));
      }), button('Remove peer', async () => { await call('remove', { id: peer.id }); notice('Peer removed.'); }));
      list.append(row);
    }
    renderNotes(element('peer-published'), status.published, false);
    renderNotes(element('peer-inbox'), status.inbox, true);
  }
  async function run(action) {
    if (box.dataset.busy) return;
    box.dataset.busy = 'true'; box.setAttribute('aria-busy', 'true');
    notice('Working on the requested peer operation…');
    try { await action(); await refresh(); }
    catch (error) { notice(error.message); }
    finally { delete box.dataset.busy; box.removeAttribute('aria-busy'); }
  }
  element('peer-apply').addEventListener('click', () => run(async () => {
    await call('config', { enabled: element('peer-enabled').checked });
    notice(element('peer-enabled').checked ? 'Enabled. Only dedicated receive-key holders can exchange explicitly published notes.' : 'Disabled. No peer requests are sent or accepted. Local work continues.');
  }));
  element('peer-key-create').addEventListener('click', () => run(async () => {
    const result = await call('key', { revoke: false });
    element('peer-receive-key').value = result.receive_key;
    notice('New receive key created. Copy it once to your trusted peers; any previous receive key is revoked.');
  }));
  element('peer-key-revoke').addEventListener('click', () => run(async () => {
    await call('key', { revoke: true }); element('peer-receive-key').value = ''; notice('Receive key revoked.');
  }));
  element('peer-key-copy').addEventListener('click', async () => {
    if (!element('peer-receive-key').value) { notice('Create a receive key before copying it.'); return; }
    try { await navigator.clipboard.writeText(element('peer-receive-key').value); notice('Receive key copied. Share privately with trusted peers only.'); }
    catch (_) { notice('Select the receive-key field and copy it manually.'); }
  });
  element('peer-add').addEventListener('click', () => run(async () => {
    await call('add', { label: element('peer-label').value.trim(), origin: element('peer-origin').value.trim(), token: element('peer-recipient-key').value.trim() });
    element('peer-recipient-key').value = ''; notice('Trusted peer saved locally. No request was sent.');
  }));
  element('peer-publish').addEventListener('click', () => run(async () => {
    if (!element('peer-consent').checked) throw new Error('Approve sharing this exact note first.');
    const result = await call('publish', { title: element('peer-title').value, text: element('peer-text').value, consent: true });
    element('peer-consent').checked = false;
    notice('Note prepared locally. Review the filtered text below; exchange occurs only when you request it.');
    element('peer-title').value = result.content.title; element('peer-text').value = result.content.text;
  }));
  element('peer-refresh').addEventListener('click', () => run(async () => { notice('Local peer status refreshed.'); }));
  refresh().catch(error => notice(error.message));
})();
