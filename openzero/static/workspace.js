/* Real workbench APIs only. Credentials remain in this page's password field. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { view: 'chat', candidate: null, file: null, improvement: null, training: null,
    candidateBusy: false, trainingBusy: false, refreshingJobs: false, proposalPoll: false, jobs: [], runStarted: null, logs: 0 };
  const notice = (id, message, error = false) => { $(id).textContent = message; $(id).classList.toggle('error', error); };
  const candidateURL = suffix => '/api/improvement/candidates/' + encodeURIComponent(state.candidate.id) + (suffix || '');
  async function api(url, method = 'GET', payload) {
    const headers = { Accept: 'application/json' };
    const token = $('workbench-token').value.trim();
    if (token) headers.Authorization = 'Bearer ' + token;
    if (payload !== undefined) headers['Content-Type'] = 'application/json';
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 180000);
    try {
      const response = await fetch(url, { method, headers, credentials: 'same-origin', signal: controller.signal,
        ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}) });
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('The service did not return JSON. Check the connection and refresh status before repeating an action.'); }
      if (!response.ok || data.status === 'error') {
        const hint = response.status === 401 || response.status === 403 ? ' Use an authorized local connection or enter a session API key under Workbench access.' : '';
        throw new Error((data.error || data.message || 'Request failed (' + response.status + ')') + hint);
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('No confirmed response from the service. Refresh status before repeating this action; it may still be running.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function toggleControls(force) {
    const collapsed = force === undefined ? !document.body.classList.contains('sidebar-collapsed') : !force;
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    $('settings-toggle').setAttribute('aria-expanded', String(!collapsed));
  }
  function showView(name) {
    if (!['chat', 'improvement', 'training'].includes(name)) return;
    state.view = name;
    document.querySelectorAll('.workspace-view').forEach(panel => { panel.hidden = panel.id !== 'workspace-' + name; });
    document.querySelectorAll('.workspace-tab').forEach(button => { button.classList.toggle('active', button.dataset.workspace === name); button.setAttribute('aria-selected', String(button.dataset.workspace === name)); });
    if (name === 'improvement') refreshImprovement();
    if (name === 'training') refreshTraining();
  }
  function runState(active, status, message) {
    if (active && state.runStarted === null) { state.runStarted = Date.now(); state.logs = 0; $('activity-count').textContent = '0 updates this run'; }
    $('run-state').textContent = status === 'stopping' ? 'Stopping' : active ? 'Working' : status === 'error' || status === 'failed' ? 'Needs attention' : 'Ready';
    $('run-state').classList.toggle('running', active);
    $('run-state').classList.toggle('failed', ['error', 'failed'].includes(status));
    $('run-detail').textContent = message || (active ? 'Waiting for a reported task update…' : 'Choose a model and describe the outcome you want.');
    $('run-detail').title = $('run-detail').textContent;
    if (!active && state.runStarted !== null) { $('run-elapsed').textContent = Math.round((Date.now() - state.runStarted) / 1000) + 's total'; state.runStarted = null; }
  }
  window.openzeroWorkspace = { runState, activity() { state.logs++; $('activity-count').textContent = state.logs + ' updates this run'; } };
  function hasUnsavedFile() { return state.file && $('candidate-content').value !== state.file.content; }
  function allowDiscard() { return !hasUnsavedFile() || window.confirm('Discard the unsaved candidate file edit?'); }
  function candidateControls() {
    const candidate = state.candidate, proposing = candidate && (candidate.state === 'proposing' || candidate.proposal?.status === 'running');
    const busy = state.candidateBusy || proposing;
    $('candidate-create').disabled = !state.improvement?.enabled || busy;
    ['candidate-file', 'candidate-load-file', 'candidate-syntax', 'candidate-tests'].forEach(id => { $(id).disabled = !candidate || busy; });
    $('candidate-content').disabled = !state.file || busy;
    $('candidate-content').readOnly = state.file?.editable === false;
    $('candidate-save-file').disabled = !state.file || state.file.editable === false || busy;
    $('candidate-propose').disabled = !state.file || state.file.editable === false || busy || !state.improvement?.model_proposals;
    $('candidate-confirm').disabled = !candidate || busy;
    $('candidate-apply').disabled = !candidate || busy || !$('candidate-confirm').checked || !candidate.changes?.length || candidate.state !== 'checked' || candidate.checks?.status !== 'passed' || candidate.checks?.review_digest !== candidate.review_digest;
    $('candidate-rollback').disabled = !candidate || busy || !$('candidate-confirm').checked || candidate.state !== 'applied';
  }
  function renderCandidate(candidate) {
    if (!candidate || !candidate.id) throw new Error('The service returned no candidate identity.');
    const previous = state.candidate;
    if (!previous || previous.id !== candidate.id || previous.review_digest !== candidate.review_digest) {
      state.file = null; $('candidate-content').value = ''; $('candidate-confirm').checked = false;
    }
    state.candidate = candidate;
    $('candidate-title').textContent = 'Candidate ' + candidate.id.slice(0, 12);
    $('candidate-description').textContent = candidate.objective + '\nReview digest: ' + candidate.review_digest;
    $('candidate-state').textContent = candidate.proposal?.status === 'running' ? 'Generating proposal' : candidate.state;
    $('candidate-state').classList.toggle('running', candidate.proposal?.status === 'running');
    const previousFile = $('candidate-file').value;
    $('candidate-file').replaceChildren();
    for (const path of candidate.files || []) { const option = document.createElement('option'); option.value = path; option.textContent = path; $('candidate-file').append(option); }
    if ([...$('candidate-file').options].some(option => option.value === previousFile)) $('candidate-file').value = previousFile;
    $('candidate-diff').textContent = candidate.diff || 'No differences from the source snapshot.';
    const checks = candidate.checks;
    $('candidate-checks').textContent = checks ? `${checks.kind}: ${checks.status} · exit ${checks.exit_code ?? 'unknown'}\n${checks.output || ''}\nFunctional validation: ${checks.functional_validation || 'not reported'}` : 'No check result is recorded for this candidate.';
    if (candidate.proposal?.status === 'failed') notice('improvement-status', 'Model proposal failed: ' + (candidate.proposal.error || 'See candidate details.'), true);
    if (candidate.restart_required) notice('improvement-status', 'Source changes are applied. The running service has not been restarted; review deployment and restart separately.');
    candidateControls();
  }
  async function refreshCandidates() {
    const data = await api('/api/improvement/candidates');
    $('candidate-list').replaceChildren();
    for (const candidate of data.candidates || []) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'record-button';
      button.classList.toggle('active', candidate.id === state.candidate?.id);
      const title = document.createElement('span'); title.textContent = candidate.objective;
      const meta = document.createElement('small'); meta.textContent = candidate.id.slice(0, 12) + ' · ' + candidate.state;
      button.append(title, meta); button.addEventListener('click', async () => {
        if (state.candidateBusy || !allowDiscard()) return;
        await candidateAction('Loading candidate…', async () => { renderCandidate((await api('/api/improvement/candidates/' + encodeURIComponent(candidate.id))).candidate); });
      }); $('candidate-list').append(button);
    }
    if (!$('candidate-list').childElementCount) { const note = document.createElement('p'); note.className = 'muted'; note.textContent = 'No source candidates yet. Create one with a specific objective.'; $('candidate-list').append(note); }
  }
  async function refreshImprovement() {
    try {
      state.improvement = await api('/api/improvement/status');
      notice('improvement-status', 'Candidate workspace available. ' + (state.improvement.model_proposals ? 'Model proposals can edit a selected candidate file.' : 'Model proposals are unavailable; candidate files can be edited manually.') + ' Checks run with server-user permissions.');
      await refreshCandidates();
    } catch (error) { state.improvement = null; notice('improvement-status', error.message, true); }
    candidateControls();
  }
  async function candidateAction(message, operation, success) {
    if (state.candidateBusy) return;
    state.candidateBusy = true; candidateControls(); notice('improvement-status', message);
    try { await operation(); if (success) notice('improvement-status', success); await refreshCandidates(); return true; }
    catch (error) { notice('improvement-status', error.message, true); return false; }
    finally { state.candidateBusy = false; candidateControls(); }
  }
  async function loadCandidateFile() {
    if (!state.candidate || !allowDiscard()) return;
    await candidateAction('Loading the candidate file…', async () => {
      const data = await api(candidateURL('/file') + '?path=' + encodeURIComponent($('candidate-file').value));
      state.file = data.file; $('candidate-content').value = data.file.content;
      $('candidate-save-note').textContent = 'Loaded: ' + data.file.path + ' · ' + (data.file.editable === false ? 'Protected file: review only.' : 'SHA-256: ' + data.file.sha256);
    }, 'Candidate file loaded. Edits affect this candidate only.');
  }
  function trainingControls() {
    const lora = $('training-backend').value === 'lora';
    $('fixture-fields').hidden = lora; $('lora-fields').hidden = !lora;
    const backend = state.training?.backends?.[lora ? 'lora' : 'fixture'];
    $('training-backend-note').textContent = lora ? (backend?.available ? 'Uses reviewed local model and dataset files. Check the limits below before starting.' : 'LoRA unavailable: ' + (backend?.missing_dependencies?.join(', ') || 'check service status and dependencies.')) : 'The fixture is a small synthetic exercise, not an improvement to your language model.';
    if (lora && backend?.limits) $('training-backend-note').textContent += ' Limits: ' + JSON.stringify(backend.limits);
    const active = state.jobs.some(job => ['queued', 'running', 'cancelling'].includes(job.status));
    $('training-start').disabled = state.trainingBusy || !backend?.available || !$('training-confirm').checked || active;
  }
  function renderJobs(jobs) {
    state.jobs = jobs; $('training-jobs').replaceChildren();
    for (const job of jobs) {
      const card = document.createElement('article'); card.className = 'job-card';
      const heading = document.createElement('h4'); heading.textContent = job.backend + ' · ' + job.status + ' · ' + job.id.slice(0, 12); card.append(heading);
      const progress = job.progress || {};
      if (Number.isFinite(progress.step) && Number.isFinite(progress.total_steps) && progress.total_steps > 0) {
        const meter = document.createElement('progress'); meter.max = progress.total_steps; meter.value = progress.step; meter.setAttribute('aria-label', 'Reported training steps'); card.append(meter);
        const label = document.createElement('p'); label.textContent = progress.step + ' / ' + progress.total_steps + ' reported steps'; card.append(label);
      }
      if (job.backend === 'fixture') { const note = document.createElement('p'); note.textContent = 'Synthetic fixture: these results do not establish language-model improvement.'; card.append(note); }
      if (job.error || job.result) { const output = document.createElement('pre'); output.textContent = job.error ? 'Failure: ' + job.error : JSON.stringify(job.result, null, 2); card.append(output); }
      if (['queued', 'running', 'cancelling'].includes(job.status)) {
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'quiet-button'; cancel.textContent = 'Request cancellation';
        cancel.addEventListener('click', async () => { cancel.disabled = true; try { await api('/api/training/jobs/' + encodeURIComponent(job.id) + '/cancel', 'POST', {}); await refreshJobs(); } catch (error) { notice('training-status', error.message, true); cancel.disabled = false; } }); card.append(cancel);
      }
      $('training-jobs').append(card);
    }
    if (!jobs.length) { const note = document.createElement('p'); note.className = 'muted'; note.textContent = 'No training jobs recorded. Starting a job is an explicit action.'; $('training-jobs').append(note); }
    trainingControls();
  }
  async function refreshJobs() {
    if (state.refreshingJobs) return;
    state.refreshingJobs = true;
    try { const data = await api('/api/training/jobs'); renderJobs(data.jobs || []); }
    catch (error) { notice('training-status', error.message, true); }
    finally { state.refreshingJobs = false; }
  }
  async function refreshTraining() {
    try {
      state.training = await api('/api/training/status');
      const available = Object.entries(state.training.backends || {}).filter(([, backend]) => backend.available).map(([name]) => name);
      notice('training-status', 'Available backends: ' + (available.join(', ') || 'none') + '. Maximum active jobs: ' + (state.training.limits?.max_active_jobs ?? 'not reported') + '. Nothing starts until you confirm a job.');
      await refreshJobs();
    } catch (error) { state.training = null; notice('training-status', error.message, true); }
    trainingControls();
  }
  const integer = id => { const value = Number($(id).value); if (!Number.isInteger(value)) throw new Error('Enter a whole number for ' + id.replaceAll('training-', '').replaceAll('-', ' ') + '.'); return value; };
  $('settings-toggle').addEventListener('click', () => toggleControls());
  if (window.matchMedia('(max-width: 760px)').matches) toggleControls(false);
  document.querySelectorAll('.workspace-tab').forEach(button => button.addEventListener('click', () => showView(button.dataset.workspace)));
  document.querySelectorAll('[data-starter]').forEach(button => button.addEventListener('click', () => { $('cmd-input').value = button.dataset.starter; $('cmd-input').focus(); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !document.body.classList.contains('sidebar-collapsed') && window.matchMedia('(max-width:760px)').matches) toggleControls(false); });
  $('candidate-refresh').addEventListener('click', refreshImprovement);
  $('candidate-create').addEventListener('click', async () => {
    const objective = $('candidate-objective').value.trim();
    if (!objective) { notice('improvement-status', 'Describe the improvement objective first.', true); $('candidate-objective').focus(); return; }
    if (!allowDiscard()) return;
    await candidateAction('Creating a separate source candidate…', async () => renderCandidate((await api('/api/improvement/candidates', 'POST', { objective })).candidate), 'Candidate created. Load a file to edit it or request a model proposal.');
  });
  $('candidate-load-file').addEventListener('click', loadCandidateFile);
  $('candidate-save-file').addEventListener('click', () => candidateAction('Saving with the loaded file hash…', async () => {
    renderCandidate((await api(candidateURL('/edit'), 'POST', { path: state.file.path, content: $('candidate-content').value, expected_sha256: state.file.sha256 })).candidate);
  }, 'Candidate file saved. Reload the file before another edit; run checks and review the new diff.'));
  $('candidate-propose').addEventListener('click', async () => {
    if (hasUnsavedFile()) { notice('improvement-status', 'Save or discard your manual edit before requesting a model proposal.', true); return; }
    await candidateAction('Requesting a model proposal for the selected candidate file…', async () => {
      renderCandidate((await api(candidateURL('/propose'), 'POST', { path: state.file.path, expected_sha256: state.file.sha256, review_digest: state.candidate.review_digest })).candidate);
    }, 'Proposal requested. The model edits the candidate only; inspect the resulting diff before checks or applying.');
  });
  for (const [id, kind] of [['candidate-syntax', 'syntax'], ['candidate-tests', 'tests']]) $(id).addEventListener('click', async () => {
    if (hasUnsavedFile()) { notice('improvement-status', 'Save your file before checking the candidate.', true); return; }
    $('candidate-confirm').checked = false;
    const completed = await candidateAction('Running ' + kind + ' checks; waiting for the recorded result…', async () => renderCandidate((await api(candidateURL('/check'), 'POST', { kind })).candidate));
    if (completed && state.candidate?.checks) notice('improvement-status', kind + ' checks: ' + state.candidate.checks.status + '. Review the actual output below.', state.candidate.checks.status !== 'passed');
  });
  $('candidate-confirm').addEventListener('change', candidateControls);
  for (const action of ['apply', 'rollback']) $('candidate-' + action).addEventListener('click', async () => {
    if (hasUnsavedFile()) { notice('improvement-status', 'Save or discard the manual edit and review the candidate again.', true); return; }
    if (!window.confirm(action === 'apply' ? 'Apply this reviewed candidate to the live source? The service will not restart automatically.' : 'Roll back this candidate\'s applied files? The backend will reject files changed since application.')) return;
    await candidateAction(action === 'apply' ? 'Applying the reviewed digest…' : 'Requesting rollback…', async () => {
      renderCandidate((await api(candidateURL('/' + action), 'POST', { review_digest: state.candidate.review_digest, confirm: true })).candidate);
      $('candidate-confirm').checked = false;
    }, action === 'apply' ? 'Candidate applied. Running service restart is a separate deployment step.' : 'Rollback recorded. Review source and deployment state before restarting.');
  });
  $('training-refresh').addEventListener('click', refreshTraining);
  $('training-backend').addEventListener('change', () => { $('training-confirm').checked = false; trainingControls(); });
  $('training-confirm').addEventListener('change', trainingControls);
  $('training-start').addEventListener('click', async () => {
    if (state.trainingBusy || !$('training-confirm').checked) return;
    try {
      const backend = $('training-backend').value;
      const payload = backend === 'fixture' ? { backend, steps: integer('training-fixture-steps'), seed: integer('training-seed') } : {
        backend, base_model_path: $('training-base').value.trim(), dataset_path: $('training-dataset').value.trim(),
        steps: integer('training-steps'), rank: integer('training-rank'), max_length: integer('training-length'), learning_rate: Number($('training-rate').value) };
      if (backend === 'lora' && (!payload.base_model_path || !payload.dataset_path)) throw new Error('Provide both the reviewed local model directory and dataset path.');
      state.trainingBusy = true; trainingControls(); notice('training-status', 'Submitting the local training job…');
      const data = await api('/api/training/jobs', 'POST', payload);
      $('training-confirm').checked = false;
      notice('training-status', 'Job ' + data.job.id + ' is ' + data.job.status + '. Results appear in its job record.');
      await refreshJobs();
    } catch (error) { notice('training-status', error.message, true); }
    finally { state.trainingBusy = false; trainingControls(); }
  });
  if (typeof socket !== 'undefined') {
    const connected = value => { $('connection-state').textContent = value ? '● Connected' : '○ Disconnected'; $('connection-state').classList.toggle('online', value); $('connection-state').classList.toggle('offline', !value); };
    socket.on('connect', () => connected(true)); socket.on('disconnect', () => connected(false)); socket.on('connect_error', () => connected(false)); connected(socket.connected);
  }
  setInterval(() => {
    if (state.runStarted !== null) $('run-elapsed').textContent = Math.round((Date.now() - state.runStarted) / 1000) + 's elapsed';
  }, 1000);
  setInterval(async () => {
    if (document.hidden) return;
    if (state.view === 'training' && state.jobs.some(job => ['queued', 'running', 'cancelling'].includes(job.status))) await refreshJobs();
    if (state.view === 'improvement' && state.candidate?.proposal?.status === 'running' && !state.candidateBusy && !state.proposalPoll) {
      state.proposalPoll = true;
      try { const data = await api(candidateURL('')); renderCandidate(data.candidate); if (data.candidate.proposal?.status === 'ready') notice('improvement-status', 'Model proposal ready. Review the diff and run checks before applying.'); }
      catch (error) { notice('improvement-status', error.message, true); }
      finally { state.proposalPoll = false; }
    }
  }, 5000);
  candidateControls(); trainingControls();
})();
