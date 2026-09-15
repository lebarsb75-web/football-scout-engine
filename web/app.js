const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = { file: null, objectUrl: null, target: null, jobId: localStorage.getItem('footballScoutJobId'), pollTimer: null };
const panels = { upload: $('#upload-panel'), player: $('#video-panel'), confirm: $('#confirm-panel'), progress: $('#progress-panel') };
const video = $('#video');
const marker = $('#target-marker');

function formatTime(value) {
  if (!Number.isFinite(value)) return '—';
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, '0');
  return hours ? `${hours}:${minutes.toString().padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}

function formatBytes(bytes) {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} Go` : `${(bytes / 1024 ** 2).toFixed(1)} Mo`;
}

function showToast(message, tone = 'error') {
  const toast = $('#toast');
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.classList.remove('hidden');
  window.setTimeout(() => toast.classList.add('hidden'), 5000);
}

function showView(name) {
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === `view-${name}`));
  $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.viewTarget === name));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showPanel(name) {
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle('hidden', key !== name));
  $$('.steps li').forEach((item) => {
    const order = ['upload', 'player', 'confirm', 'progress'];
    const current = order.indexOf(name);
    const own = order.indexOf(item.dataset.step);
    item.classList.toggle('active', own === current);
    item.classList.toggle('complete', own < current);
  });
}

$$('[data-view-target]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.viewTarget)));

function resetSelection() {
  state.target = null;
  marker.classList.add('hidden');
  $('#selected-time').textContent = '—';
  $('#selected-position').textContent = 'En attente';
  $('#clear-selection').disabled = true;
  $('#video-hint').classList.remove('hidden');
}

function loadVideo(file) {
  if (!file || !file.type.startsWith('video/')) return showToast('Choisis un fichier vidéo compatible.');
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.file = file;
  state.objectUrl = URL.createObjectURL(file);
  video.src = state.objectUrl;
  $('#file-name').textContent = file.name;
  $('#file-meta').textContent = formatBytes(file.size);
  resetSelection();
  showPanel('player');
}

$('#video-input').addEventListener('change', (event) => loadVideo(event.target.files?.[0]));
['dragenter', 'dragover'].forEach((name) => $('#dropzone').addEventListener(name, (event) => { event.preventDefault(); $('#dropzone').classList.add('dragging'); }));
['dragleave', 'drop'].forEach((name) => $('#dropzone').addEventListener(name, (event) => { event.preventDefault(); $('#dropzone').classList.remove('dragging'); }));
$('#dropzone').addEventListener('drop', (event) => loadVideo(event.dataTransfer?.files?.[0]));
$('#replace-video').addEventListener('click', () => { showPanel('upload'); $('#video-input').click(); });
$('#clear-selection').addEventListener('click', resetSelection);
$('#back-to-player').addEventListener('click', () => showPanel('player'));

video.addEventListener('loadedmetadata', () => { $('#file-meta').textContent = `${formatBytes(state.file.size)} · ${formatTime(video.duration)}`; });
$('#video-stage').addEventListener('click', (event) => {
  if (!state.file || video.readyState < 2) return;
  const rect = video.getBoundingClientRect();
  const videoRatio = video.videoWidth / video.videoHeight;
  const elementRatio = rect.width / rect.height;
  let width = rect.width; let height = rect.height; let offsetX = 0; let offsetY = 0;
  if (elementRatio > videoRatio) { width = rect.height * videoRatio; offsetX = (rect.width - width) / 2; }
  else { height = rect.width / videoRatio; offsetY = (rect.height - height) / 2; }
  const x = event.clientX - rect.left - offsetX;
  const y = event.clientY - rect.top - offsetY;
  if (x < 0 || y < 0 || x > width || y > height) return;
  video.pause();
  state.target = { x: x / width, y: y / height, time: video.currentTime };
  marker.style.left = `${offsetX + x}px`; marker.style.top = `${offsetY + y}px`;
  marker.classList.remove('hidden'); $('#video-hint').classList.add('hidden');
  $('#selected-time').textContent = formatTime(state.target.time);
  $('#selected-position').textContent = `${(state.target.x * 100).toFixed(1)} % · ${(state.target.y * 100).toFixed(1)} %`;
  $('#clear-selection').disabled = false;
  $('#summary-file').textContent = state.file.name;
  $('#summary-duration').textContent = formatTime(video.duration);
  $('#summary-time').textContent = formatTime(state.target.time);
  window.setTimeout(() => showPanel('confirm'), 350);
});

function apiBase() { return $('#api-base').value.trim().replace(/\/$/, ''); }
async function api(path, options = {}) {
  const response = await fetch(`${apiBase()}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.message || `Erreur serveur (${response.status})`);
  return body;
}

function idempotencyKey() {
  const existing = sessionStorage.getItem('footballScoutIdempotencyKey');
  if (existing) return existing;
  const key = crypto.randomUUID(); sessionStorage.setItem('footballScoutIdempotencyKey', key); return key;
}

$('#start-analysis').addEventListener('click', async () => {
  const button = $('#start-analysis');
  const videoUrl = $('#video-url').value.trim();
  if (!state.target || !Number.isFinite(video.duration)) return showToast('Sélectionne d’abord le joueur.');
  if (!videoUrl) return showToast('Ajoute l’URL sécurisée générée par le stockage pour lancer le backend.');
  button.disabled = true; button.textContent = 'Vérification…';
  try {
    const estimate = await api('/analysis/estimate', { method: 'POST', body: JSON.stringify({ video_duration_seconds: video.duration }) });
    if (!estimate.ready) throw new Error('Le benchmark de coût requis n’est pas encore disponible. Aucun GPU n’a été lancé.');
    const approvedMaximum = Number(estimate.recommended_max_authorization_usd);
    $('#estimate-box').innerHTML = `<strong>Estimation validée</strong><span>Plafond recommandé : ${approvedMaximum.toFixed(2)} $</span>`;
    $('#estimate-box').classList.remove('hidden');
    const payload = { video_url: videoUrl, video_duration_seconds: video.duration, target_time_seconds: state.target.time, target: { x: state.target.x, y: state.target.y }, sample_fps: 5, confidence: 0.22, image_size: 960, approved_max_cost_usd: approvedMaximum };
    const submitted = await api('/analysis/submit', { method: 'POST', headers: { 'X-Idempotency-Key': idempotencyKey(), 'X-Cost-Approval-Secret': $('#cost-secret').value }, body: JSON.stringify(payload) });
    state.jobId = submitted.job.job_id; localStorage.setItem('footballScoutJobId', state.jobId); $('#resume-job').hidden = false;
    showPanel('progress'); updateProgress(submitted.job.status); pollJob();
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; button.innerHTML = 'Vérifier et lancer <span>→</span>'; }
});

function updateProgress(status) {
  const values = { submitted: [12, 'Envoi sécurisé'], queued: [24, 'Dans la file d’attente'], running: [66, 'Suivi du joueur'], completed: [100, 'Rapport prêt'] };
  const [percent, label] = values[status] || [18, 'Préparation'];
  $('#progress-bar').style.width = `${percent}%`; $('#progress-percent').textContent = `${percent} %`; $('#progress-state').textContent = label;
  $('#progress-title').textContent = status === 'running' ? 'Le moteur suit le joueur sélectionné.' : status === 'queued' ? 'Ton match est dans la file d’attente.' : 'Préparation de l’analyse.';
  $('#stage-tracking').classList.toggle('done', percent >= 66); $('#stage-quality').classList.toggle('done', percent >= 85); $('#stage-report').classList.toggle('done', percent === 100);
}

async function pollJob() {
  clearTimeout(state.pollTimer);
  if (!state.jobId) return;
  try {
    const job = await api(`/analysis/jobs/${encodeURIComponent(state.jobId)}/refresh`, { method: 'POST' });
    updateProgress(job.status);
    if (job.status === 'completed' && job.result) return renderResult(job.result);
    if (['failed', 'timed_out', 'cancelled'].includes(job.status)) return renderFailure('Le traitement n’a pas abouti', 'Aucune statistique n’est affichée. Tu peux vérifier la vidéo puis recommencer sans interpréter ce résultat.');
    state.pollTimer = window.setTimeout(pollJob, 3500);
  } catch (error) { renderFailure('Impossible de suivre l’analyse', `${error.message}. Aucun nouvel envoi n’a été effectué.`); }
}

function metricCard(title, metric, formatter, lockedReason) {
  if (!metric?.available) return `<article class="metric-card locked"><span>${title}</span><strong>Masquée</strong><small>🔒 ${lockedReason}</small></article>`;
  return `<article class="metric-card"><span>${title}</span><strong>${formatter(metric.value)}</strong><small>✓ Gate de fiabilité passé</small></article>`;
}

function renderResult(result) {
  clearTimeout(state.pollTimer); showView('results');
  if (result.status !== 'ready') return renderFailure('Analyse non exploitable', 'Le suivi du joueur n’a pas franchi tous les contrôles de continuité. Les statistiques sont volontairement masquées.', result);
  const metrics = result.metrics || {}; const quality = result.quality || {};
  $('#result-content').innerHTML = `<div class="result-head"><div><p class="eyebrow">RAPPORT JOUEUR</p><h1>Analyse terminée.</h1><p>Seules les métriques ayant franchi leur gate sont affichées.</p></div><span class="quality-pill">✓ Suivi validé</span></div>
    <div class="result-summary"><div class="quality-score"><span>Qualité du suivi</span><strong>${Number(quality.player_tracking_score_percent).toFixed(0)}<small>%</small></strong><p>Couverture diagnostique : ${Number(quality.tracking_coverage_percent).toFixed(1)} %</p></div><div class="metrics-grid">
    ${metricCard('Distance parcourue', metrics.distance_meters, (v) => `${(v / 1000).toFixed(2).replace('.', ',')} km`, 'Calibration terrain requise')}
    ${metricCard('Touches de balle', metrics.ball_touches, (v) => String(v), 'Visibilité ballon insuffisante')}
    ${metricCard('Temps de possession', metrics.possession_seconds, (v) => formatTime(v), 'Gate ballon non atteint')}
    </div></div>
    <section class="quality-explain"><div><p class="eyebrow">TRANSPARENCE</p><h2>Pourquoi certaines données sont masquées</h2><p>La distance exige une calibration valide. Les touches et la possession exigent un suivi joueur fiable et une visibilité suffisante du ballon.</p></div><div class="gate-list"><span class="pass">✓ Continuité joueur</span><span class="${quality.ball_metrics_pass ? 'pass' : 'locked'}">${quality.ball_metrics_pass ? '✓' : '—'} Ballon</span><span class="${quality.pitch_calibration_used ? 'pass' : 'locked'}">${quality.pitch_calibration_used ? '✓' : '—'} Calibration</span></div></section>
    <div class="action-row"><button class="secondary" id="new-analysis">Nouvelle analyse</button></div>`;
  $('#new-analysis').addEventListener('click', newAnalysis);
}

function renderFailure(title, message, result = null) {
  showView('results');
  const coverage = result?.quality?.tracking_coverage_percent;
  $('#result-content').innerHTML = `<div class="failure-card"><div class="failure-icon">!</div><p class="eyebrow">RÉSULTAT PROTÉGÉ</p><h1>${title}</h1><p>${message}</p>${Number.isFinite(coverage) ? `<div class="diagnostic">Couverture détectée : <strong>${coverage.toFixed(1)} %</strong><small>Indicateur technique, pas une statistique de performance.</small></div>` : ''}<button class="primary" id="retry-analysis">Préparer une nouvelle analyse</button></div>`;
  $('#retry-analysis').addEventListener('click', newAnalysis);
}

function newAnalysis() {
  localStorage.removeItem('footballScoutJobId'); sessionStorage.removeItem('footballScoutIdempotencyKey'); state.jobId = null; $('#resume-job').hidden = true; showView('analysis'); showPanel('upload');
}

$('#stop-polling').addEventListener('click', () => { clearTimeout(state.pollTimer); showToast('Suivi à l’écran arrêté. Le job n’a pas été relancé.', 'info'); });
$('#resume-job').addEventListener('click', () => { showView('analysis'); showPanel('progress'); pollJob(); });
if (state.jobId) $('#resume-job').hidden = false;
window.addEventListener('beforeunload', () => { if (state.objectUrl) URL.revokeObjectURL(state.objectUrl); clearTimeout(state.pollTimer); });
