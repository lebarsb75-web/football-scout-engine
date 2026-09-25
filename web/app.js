const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  file: null,
  objectUrl: null,
  target: null,
  jobId: localStorage.getItem('footballScoutJobId'),
  pollTimer: null,
  activeJob: null,
  lastResult: null,
  lastSummary: null,
  uploadController: null,
};

const panels = {
  upload: $('#upload-panel'),
  player: $('#video-panel'),
  confirm: $('#confirm-panel'),
  progress: $('#progress-panel'),
};
const video = $('#video');
const marker = $('#target-marker');
const identityFieldIds = [
  'player-name',
  'player-position',
  'player-team',
  'match-opponent',
  'match-date',
  'shirt-number',
];

function formatTime(value) {
  if (!Number.isFinite(value)) return '—';
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, '0');
  return hours
    ? `${hours}:${minutes.toString().padStart(2, '0')}:${seconds}`
    : `${minutes}:${seconds}`;
}

function formatBytes(bytes) {
  return bytes >= 1024 ** 3
    ? `${(bytes / 1024 ** 3).toFixed(1)} Go`
    : `${(bytes / 1024 ** 2).toFixed(1)} Mo`;
}

function formatDate(value, includeTime = false) {
  if (!value) return '';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(includeTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function showToast(message, tone = 'error') {
  const toast = $('#toast');
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 5000);
}

function showView(name) {
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === `view-${name}`));
  $$('.nav-link').forEach((link) => link.classList.toggle('active', link.dataset.viewTarget === name));
  scrollTo({ top: 0, behavior: 'smooth' });
}

function showPanel(name) {
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle('hidden', key !== name));
  const order = ['upload', 'player', 'confirm', 'progress'];
  $$('.steps li').forEach((item) => {
    const current = order.indexOf(name);
    const position = order.indexOf(item.dataset.step);
    item.classList.toggle('active', position === current);
    item.classList.toggle('complete', position < current);
  });
}

$$('[data-view-target]').forEach((button) => button.addEventListener('click', () => {
  const target = button.dataset.viewTarget;
  showView(target);
  if (target === 'history') loadHistory();
}));

function resetSelection() {
  state.target = null;
  marker.classList.add('hidden');
  $('#selected-time').textContent = '—';
  $('#selected-position').textContent = 'En attente';
  $('#clear-selection').disabled = true;
  $('#confirm-player').disabled = true;
  $('#selection-status').textContent = 'Clique sur le joueur pour continuer.';
  $('#video-hint').classList.remove('hidden');
}

function loadVideo(file) {
  if (!file || !file.type.startsWith('video/')) {
    showToast('Choisis un fichier vidéo compatible.');
    return;
  }
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.file = file;
  state.objectUrl = URL.createObjectURL(file);
  video.src = state.objectUrl;
  $('#file-name').textContent = file.name;
  $('#file-meta').textContent = formatBytes(file.size);
  $('#upload-progress').classList.add('hidden');
  $('#estimate-box').classList.add('hidden');
  resetSelection();
  showView('analysis');
  showPanel('player');
}

$('#video-input').addEventListener('change', (event) => loadVideo(event.target.files?.[0]));
['dragenter', 'dragover'].forEach((name) => $('#dropzone').addEventListener(name, (event) => {
  event.preventDefault();
  $('#dropzone').classList.add('dragging');
}));
['dragleave', 'drop'].forEach((name) => $('#dropzone').addEventListener(name, (event) => {
  event.preventDefault();
  $('#dropzone').classList.remove('dragging');
}));
$('#dropzone').addEventListener('drop', (event) => loadVideo(event.dataTransfer?.files?.[0]));
$('#replace-video').addEventListener('click', () => $('#video-input').click());
$('#clear-selection').addEventListener('click', resetSelection);
$('#back-to-player').addEventListener('click', () => showPanel('player'));

video.addEventListener('loadedmetadata', () => {
  $('#file-meta').textContent = `${formatBytes(state.file.size)} · ${formatTime(video.duration)}`;
});

$('#video-stage').addEventListener('click', (event) => {
  if (!state.file || video.readyState < 2) return;
  const rect = video.getBoundingClientRect();
  const videoRatio = video.videoWidth / video.videoHeight;
  const elementRatio = rect.width / rect.height;
  let width = rect.width;
  let height = rect.height;
  let offsetX = 0;
  let offsetY = 0;
  if (elementRatio > videoRatio) {
    width = rect.height * videoRatio;
    offsetX = (rect.width - width) / 2;
  } else {
    height = rect.width / videoRatio;
    offsetY = (rect.height - height) / 2;
  }
  const x = event.clientX - rect.left - offsetX;
  const y = event.clientY - rect.top - offsetY;
  if (x < 0 || y < 0 || x > width || y > height) return;
  video.pause();
  state.target = { x: x / width, y: y / height, time: video.currentTime };
  marker.style.left = `${offsetX + x}px`;
  marker.style.top = `${offsetY + y}px`;
  marker.classList.remove('hidden');
  $('#video-hint').classList.add('hidden');
  $('#selected-time').textContent = formatTime(state.target.time);
  $('#selected-position').textContent = `${(state.target.x * 100).toFixed(1)} % · ${(state.target.y * 100).toFixed(1)} %`;
  $('#clear-selection').disabled = false;
  $('#confirm-player').disabled = false;
  $('#selection-status').textContent = '✓ Joueur sélectionné. Vérifie le repère puis confirme.';
  $('#summary-file').textContent = state.file.name;
  $('#summary-duration').textContent = formatTime(video.duration);
  $('#summary-time').textContent = formatTime(state.target.time);
});

$('#confirm-player').addEventListener('click', () => {
  if (!state.target) return showToast('Clique d’abord sur le joueur.');
  showPanel('confirm');
  if (!$('#player-name').value) $('#player-name').focus();
});

function restoreIdentityDraft() {
  let draft = {};
  try {
    draft = JSON.parse(localStorage.getItem('footballScoutIdentityDraft') || '{}');
  } catch (_) {
    draft = {};
  }
  identityFieldIds.forEach((id) => {
    if (draft[id] !== undefined) $(`#${id}`).value = draft[id];
  });
}

function saveIdentityDraft() {
  const draft = {};
  identityFieldIds.forEach((id) => { draft[id] = $(`#${id}`).value.trim(); });
  localStorage.setItem('footballScoutIdentityDraft', JSON.stringify(draft));
}

identityFieldIds.forEach((id) => $(`#${id}`).addEventListener('input', saveIdentityDraft));
restoreIdentityDraft();

function reportIdentity() {
  const name = $('#player-name').value.trim();
  const position = $('#player-position').value.trim();
  if (!name || !position) {
    const missing = !name ? $('#player-name') : $('#player-position');
    missing.focus();
    throw new Error('Renseigne le nom et le poste du joueur.');
  }
  const shirtNumber = Number.parseInt($('#shirt-number').value, 10);
  return {
    player_profile: {
      name,
      position,
      team: $('#player-team').value.trim() || null,
      shirt_number: Number.isInteger(shirtNumber) ? shirtNumber : null,
    },
    match_context: {
      opponent: $('#match-opponent').value.trim() || null,
      match_date: $('#match-date').value || null,
      source_filename: state.file?.name || null,
    },
  };
}

const configuredApi = window.FOOTBALL_SCOUT_CONFIG?.apiBase?.trim() || '';
const savedApi = localStorage.getItem('footballScoutApiBase') || '';
if (configuredApi || savedApi) {
  $('#api-base').value = configuredApi || savedApi;
  $('#history-api-base').value = configuredApi || savedApi;
}
const savedAccessCode = sessionStorage.getItem('footballScoutAccessCode');
if (savedAccessCode) {
  $('#access-code').value = savedAccessCode;
  $('#history-access-code').value = savedAccessCode;
}
$('#api-base').addEventListener('change', () => {
  localStorage.setItem('footballScoutApiBase', $('#api-base').value.trim());
  $('#history-api-base').value = $('#api-base').value.trim();
});
$('#access-code').addEventListener('input', () => {
  sessionStorage.setItem('footballScoutAccessCode', $('#access-code').value);
  $('#history-access-code').value = $('#access-code').value;
});

function apiBase() {
  return $('#api-base').value.trim().replace(/\/$/, '');
}

function accessCode() {
  return $('#access-code').value;
}

async function api(path, options = {}) {
  if (!apiBase()) throw new Error('Le backend de production n’est pas encore configuré');
  const response = await fetch(`${apiBase()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-App-Access-Code': accessCode(),
      ...(options.headers || {}),
    },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body.detail === 'string'
      ? body.detail
      : body.detail?.message || `Erreur serveur (${response.status})`);
  }
  return body;
}

function idempotencyKey() {
  const existing = sessionStorage.getItem('footballScoutIdempotencyKey');
  if (existing) return existing;
  const key = crypto.randomUUID();
  sessionStorage.setItem('footballScoutIdempotencyKey', key);
  return key;
}

function setUploadProgress(percent, message) {
  const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
  $('#upload-progress').classList.remove('hidden');
  $('#upload-bar').style.width = `${safePercent}%`;
  $('#upload-percent').textContent = `${safePercent} %`;
  $('#upload-status').textContent = message;
}

async function completeMultipartUpload(prepared, parts) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await api(`/uploads/${encodeURIComponent(prepared.upload_id)}/complete`, {
        method: 'POST',
        headers: { 'X-Upload-Token': prepared.upload_token },
        body: JSON.stringify({ parts }),
      });
    } catch (error) {
      lastError = error;
      if (attempt === 3) break;
      setUploadProgress(90, `Connexion instable · nouvel essai d’assemblage (${attempt + 1}/3)…`);
      await new Promise((resolve) => setTimeout(resolve, attempt * 750));
    }
  }
  throw new Error(`Impossible d’assembler la vidéo après 3 essais : ${lastError.message}`);
}

async function uploadSelectedVideo() {
  const prepared = await api('/uploads', {
    method: 'POST',
    body: JSON.stringify({
      filename: state.file.name,
      content_type: state.file.type || 'application/octet-stream',
      size_bytes: state.file.size,
    }),
  });
  const partSize = Number(prepared.part_size_bytes);
  const partCount = Math.ceil(state.file.size / partSize);
  const parts = [];
  state.uploadController = new AbortController();
  try {
    for (let index = 0; index < partCount; index += 1) {
      const partNumber = index + 1;
      const start = index * partSize;
      const end = Math.min(state.file.size, start + partSize);
      setUploadProgress(5 + index / partCount * 80, `Envoi sécurisé · partie ${partNumber} sur ${partCount}`);
      const response = await fetch(`${apiBase()}/uploads/${encodeURIComponent(prepared.upload_id)}/parts/${partNumber}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/octet-stream',
          'X-Upload-Token': prepared.upload_token,
        },
        body: state.file.slice(start, end),
        signal: state.uploadController.signal,
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `Échec de l’envoi de la partie ${partNumber}`);
      parts.push(body);
    }
    setUploadProgress(90, 'Assemblage sécurisé de la vidéo…');
    const completed = await completeMultipartUpload(prepared, parts);
    setUploadProgress(100, 'Vidéo envoyée et prête pour l’analyse.');
    return completed.video_url;
  } catch (error) {
    fetch(`${apiBase()}/uploads/${encodeURIComponent(prepared.upload_id)}`, {
      method: 'DELETE',
      headers: { 'X-Upload-Token': prepared.upload_token },
    }).catch(() => {});
    throw error;
  } finally {
    state.uploadController = null;
  }
}

$('#start-analysis').addEventListener('click', async () => {
  const button = $('#start-analysis');
  if (!state.target || !Number.isFinite(video.duration)) return showToast('Sélectionne d’abord le joueur.');
  let identity;
  try {
    identity = reportIdentity();
  } catch (error) {
    return showToast(error.message);
  }
  if (!apiBase()) return showToast('Le moteur en ligne n’est pas encore connecté à cette version du site.');
  if (!accessCode()) return showToast('Saisis le code d’accès privé pour continuer.');
  button.disabled = true;
  button.textContent = 'Vérification…';
  try {
    const estimate = await api('/analysis/estimate', {
      method: 'POST',
      body: JSON.stringify({ video_duration_seconds: video.duration }),
    });
    if (!estimate.ready) throw new Error('Le benchmark de coût requis n’est pas encore disponible. Aucun GPU n’a été lancé.');
    const max = Number(estimate.recommended_max_authorization_usd);
    $('#estimate-box').innerHTML = `<strong>Estimation validée</strong><span>Plafond recommandé : ${max.toFixed(4)} $</span>`;
    $('#estimate-box').classList.remove('hidden');
    button.textContent = 'Envoi sécurisé…';
    const videoUrl = await uploadSelectedVideo();
    button.textContent = 'Lancement contrôlé…';
    const payload = {
      video_url: videoUrl,
      video_duration_seconds: video.duration,
      target_time_seconds: state.target.time,
      target: { x: state.target.x, y: state.target.y },
      sample_fps: 5,
      confidence: 0.22,
      image_size: 960,
      approved_max_cost_usd: max,
      ...identity,
    };
    const submitted = await api('/analysis/submit', {
      method: 'POST',
      headers: {
        'X-Idempotency-Key': idempotencyKey(),
      },
      body: JSON.stringify(payload),
    });
    state.jobId = submitted.job.job_id;
    state.activeJob = submitted.job;
    localStorage.setItem('footballScoutJobId', state.jobId);
    localStorage.setItem(`footballScoutJobMeta:${state.jobId}`, JSON.stringify(identity));
    $('#resume-job').hidden = false;
    showPanel('progress');
    updateProgress(submitted.job.status);
    pollJob();
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Vérifier et lancer <span>→</span>';
  }
});

function updateProgress(status) {
  const values = {
    submitted: [12, 'Envoi sécurisé'],
    queued: [24, 'Dans la file d’attente'],
    running: [66, 'Suivi du joueur'],
    completed: [100, 'Rapport prêt'],
  };
  const [percent, label] = values[status] || [18, 'Préparation'];
  $('#progress-bar').style.width = `${percent}%`;
  $('#progress-percent').textContent = `${percent} %`;
  $('#progress-state').textContent = label;
  $('#progress-title').textContent = status === 'running'
    ? 'Le moteur suit le joueur sélectionné.'
    : status === 'queued'
      ? 'Ton match est dans la file d’attente.'
      : 'Préparation de l’analyse.';
  $('#stage-tracking').classList.toggle('done', percent >= 66);
  $('#stage-quality').classList.toggle('done', percent >= 85);
  $('#stage-report').classList.toggle('done', percent === 100);
}

async function pollJob() {
  clearTimeout(state.pollTimer);
  if (!state.jobId) return;
  try {
    const job = await api(`/analysis/jobs/${encodeURIComponent(state.jobId)}/refresh`, { method: 'POST' });
    state.activeJob = job;
    updateProgress(job.status);
    if (job.status === 'completed' && job.result) return renderResult(job.result, job.request_summary, job);
    if (['failed', 'timed_out', 'cancelled'].includes(job.status)) {
      return renderFailure('Le traitement n’a pas abouti', 'Aucune statistique n’est affichée.');
    }
    state.pollTimer = setTimeout(pollJob, 3500);
  } catch (error) {
    renderFailure('Impossible de suivre l’analyse', `${error.message}. Aucun nouvel envoi n’a été effectué.`);
  }
}

function metricCard(title, metric, formatter, reason) {
  if (!metric?.available) {
    return `<article class="metric-card locked"><span>${title}</span><strong>Masquée</strong><small>🔒 ${reason}</small></article>`;
  }
  return `<article class="metric-card"><span>${title}</span><strong>${formatter(metric.value)}</strong><small>✓ Contrôle de fiabilité passé</small></article>`;
}

function summaryWithLocalFallback(summary, jobId) {
  if (summary?.player_profile) return summary;
  if (!jobId) return summary || {};
  try {
    return { ...(summary || {}), ...JSON.parse(localStorage.getItem(`footballScoutJobMeta:${jobId}`) || '{}') };
  } catch (_) {
    return summary || {};
  }
}

function renderClips(clips) {
  if (!clips?.length) return '';
  const items = clips.map((clip, index) => `<li><span>${String(index + 1).padStart(2, '0')}</span><div><strong>${clip.type === 'possession' ? 'Séquence de possession' : 'Contact avec le ballon'}</strong><small>${formatTime(Number(clip.start))} → ${formatTime(Number(clip.end))}</small></div></li>`).join('');
  return `<section class="clips-section"><div><p class="eyebrow">SÉQUENCES</p><h2>Moments détectés</h2><p>Ces fenêtres sont proposées uniquement lorsque le contrôle du ballon est validé.</p></div><ol>${items}</ol></section>`;
}

function renderResult(result, rawSummary = {}, job = state.activeJob) {
  clearTimeout(state.pollTimer);
  const summary = summaryWithLocalFallback(rawSummary, job?.job_id || state.jobId);
  state.lastResult = result;
  state.lastSummary = summary;
  showView('results');
  if (result.status !== 'ready') {
    return renderFailure(
      'Analyse à vérifier',
      'Le suivi du joueur n’a pas franchi tous les contrôles. Les statistiques sont volontairement masquées.',
      result,
    );
  }
  const metrics = result.metrics || {};
  const quality = result.quality || {};
  const player = summary.player_profile || {};
  const match = summary.match_context || {};
  const playerName = escapeHtml(player.name || 'Joueur analysé');
  const context = [player.position, player.team, match.opponent ? `vs ${match.opponent}` : '', formatDate(match.match_date)]
    .filter(Boolean)
    .map(escapeHtml)
    .join(' · ');
  const trackingScore = Number(quality.player_tracking_score_percent || 0);
  const coverage = Number(quality.tracking_coverage_percent || 0);
  $('#result-content').innerHTML = `
    <div class="result-head"><div><p class="eyebrow">RAPPORT JOUEUR</p><h1>${playerName}</h1><p>${context || 'Analyse individuelle terminée.'}</p></div><span class="quality-pill">✓ Suivi validé</span></div>
    <div class="result-summary"><div class="quality-score"><span>Qualité du suivi</span><strong>${trackingScore.toFixed(0)}<small>%</small></strong><p>Couverture : ${coverage.toFixed(1)} %</p><small class="engine-label">Moteur ${escapeHtml(result.engine_version || '—')}</small></div><div class="metrics-grid">${metricCard('Distance parcourue', metrics.distance_meters, (value) => `${(value / 1000).toFixed(2).replace('.', ',')} km`, 'Calibration terrain requise')}${metricCard('Touches de balle', metrics.ball_touches, (value) => String(value), 'Visibilité ballon insuffisante')}${metricCard('Temps de possession', metrics.possession_seconds, (value) => formatTime(value), 'Contrôle ballon non atteint')}</div></div>
    <section class="quality-explain"><div><p class="eyebrow">TRANSPARENCE</p><h2>Pourquoi certaines données sont masquées</h2><p>La distance exige une calibration valide. Les touches et la possession exigent un suivi fiable du ballon.</p></div><div class="gate-list"><span class="pass">✓ Continuité joueur</span><span class="${quality.ball_metrics_pass ? 'pass' : 'locked'}">${quality.ball_metrics_pass ? '✓' : '—'} Ballon</span><span class="${quality.pitch_calibration_used ? 'pass' : 'locked'}">${quality.pitch_calibration_used ? '✓' : '—'} Calibration</span></div></section>
    ${renderClips(result.clips)}
    <div class="action-row result-actions"><button class="secondary" id="download-json">Rapport JSON</button><button class="secondary" id="download-csv">Exporter en CSV</button><button class="primary" id="new-analysis">Nouvelle analyse</button></div>`;
  $('#new-analysis').addEventListener('click', newAnalysis);
  $('#download-json').addEventListener('click', () => downloadReport('json'));
  $('#download-csv').addEventListener('click', () => downloadReport('csv'));
}

function renderFailure(title, message, result = null) {
  showView('results');
  const coverage = Number(result?.quality?.tracking_coverage_percent);
  $('#result-content').innerHTML = `<div class="failure-card"><div class="failure-icon">!</div><p class="eyebrow">RÉSULTAT PROTÉGÉ</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(message)}</p>${Number.isFinite(coverage) ? `<div class="diagnostic">Couverture détectée : <strong>${coverage.toFixed(1)} %</strong><small>Indicateur technique, pas une statistique de performance.</small></div>` : ''}<button class="primary" id="retry-analysis">Préparer une nouvelle analyse</button></div>`;
  $('#retry-analysis').addEventListener('click', newAnalysis);
}

function downloadBlob(filename, type, content) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function reportFilename(extension) {
  const name = state.lastSummary?.player_profile?.name || 'joueur';
  const slug = name.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return `football-scout-${slug || 'joueur'}.${extension}`;
}

function downloadReport(format) {
  if (!state.lastResult) return;
  if (format === 'json') {
    downloadBlob(reportFilename('json'), 'application/json', JSON.stringify({ report: state.lastSummary, result: state.lastResult }, null, 2));
    return;
  }
  const metrics = state.lastResult.metrics || {};
  const rows = [
    ['joueur', state.lastSummary?.player_profile?.name || ''],
    ['poste', state.lastSummary?.player_profile?.position || ''],
    ['qualite_suivi_pourcent', state.lastResult.quality?.player_tracking_score_percent ?? ''],
    ['couverture_pourcent', state.lastResult.quality?.tracking_coverage_percent ?? ''],
    ['distance_metres', metrics.distance_meters?.available ? metrics.distance_meters.value : 'masquee'],
    ['touches_balle', metrics.ball_touches?.available ? metrics.ball_touches.value : 'masquee'],
    ['possession_secondes', metrics.possession_seconds?.available ? metrics.possession_seconds.value : 'masquee'],
  ];
  const csv = `\uFEFF${rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(';')).join('\n')}`;
  downloadBlob(reportFilename('csv'), 'text/csv;charset=utf-8', csv);
}

const statusLabels = {
  submitted: 'Envoyée',
  queued: 'En attente',
  running: 'En cours',
  completed: 'Terminée',
  failed: 'Échec',
  timed_out: 'Temps dépassé',
  cancelled: 'Annulée',
};

function renderHistory(jobs) {
  if (!jobs.length) {
    $('#history-list').innerHTML = '<div class="empty-state"><span>⌁</span><h2>Aucune analyse pour le moment</h2><p>Ta première analyse apparaîtra ici dès qu’elle aura été envoyée au moteur.</p><button class="primary" data-empty-analysis>Analyser un match</button></div>';
    $('[data-empty-analysis]').addEventListener('click', () => showView('analysis'));
    return;
  }
  $('#history-list').innerHTML = jobs.map((job) => {
    const summary = summaryWithLocalFallback(job.request_summary, job.job_id);
    const player = summary.player_profile || {};
    const match = summary.match_context || {};
    const details = [player.position, player.team, match.opponent ? `vs ${match.opponent}` : ''].filter(Boolean).map(escapeHtml).join(' · ');
    const status = statusLabels[job.status] || 'À vérifier';
    const safeStatus = Object.hasOwn(statusLabels, job.status) ? job.status : 'unknown';
    return `<article class="history-card"><div class="history-monogram">${escapeHtml((player.name || 'FS').split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase())}</div><div class="history-main"><div><span class="status-badge ${safeStatus}">${escapeHtml(status)}</span><small>${escapeHtml(formatDate(job.created_at, true))}</small></div><h2>${escapeHtml(player.name || 'Analyse joueur')}</h2><p>${details || `Vidéo de ${formatTime(Number(summary.video_duration_seconds))}`}</p></div><div class="history-action"><small>${job.status === 'completed' ? 'Rapport disponible' : 'Aucun nouveau job ne sera créé'}</small><button class="secondary" data-open-job="${escapeHtml(job.job_id)}">${job.status === 'completed' ? 'Voir le rapport' : 'Voir le suivi'}</button></div></article>`;
  }).join('');
  $$('[data-open-job]').forEach((button) => button.addEventListener('click', () => openExistingJob(button.dataset.openJob)));
}

async function loadHistory() {
  const connect = $('#history-connect');
  if (!apiBase() || !accessCode()) {
    connect.classList.remove('hidden');
    $('#history-list').innerHTML = '';
    return;
  }
  connect.classList.add('hidden');
  $('#history-list').innerHTML = '<div class="history-loading"><span></span><span></span><span></span><p>Chargement des analyses…</p></div>';
  try {
    const response = await api('/analysis/jobs?limit=30');
    renderHistory(response.jobs || []);
  } catch (error) {
    $('#history-list').innerHTML = `<div class="empty-state error"><span>!</span><h2>Historique indisponible</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function openExistingJob(jobId) {
  try {
    const job = await api(`/analysis/jobs/${encodeURIComponent(jobId)}`);
    state.jobId = jobId;
    state.activeJob = job;
    localStorage.setItem('footballScoutJobId', jobId);
    $('#resume-job').hidden = false;
    if (job.status === 'completed' && job.result) return renderResult(job.result, job.request_summary, job);
    if (['failed', 'timed_out', 'cancelled'].includes(job.status)) {
      return renderFailure('Le traitement n’a pas abouti', 'Aucune statistique n’est affichée.');
    }
    showView('analysis');
    showPanel('progress');
    updateProgress(job.status);
    pollJob();
  } catch (error) {
    showToast(error.message);
  }
}

function newAnalysis() {
  clearTimeout(state.pollTimer);
  state.uploadController?.abort();
  localStorage.removeItem('footballScoutJobId');
  sessionStorage.removeItem('footballScoutIdempotencyKey');
  state.jobId = null;
  state.activeJob = null;
  state.lastResult = null;
  state.lastSummary = null;
  $('#upload-progress').classList.add('hidden');
  $('#estimate-box').classList.add('hidden');
  $('#resume-job').hidden = true;
  showView('analysis');
  showPanel('upload');
}

$('#refresh-history').addEventListener('click', loadHistory);
$('#connect-history').addEventListener('click', () => {
  const base = $('#history-api-base').value.trim();
  const code = $('#history-access-code').value;
  $('#api-base').value = base;
  $('#access-code').value = code;
  localStorage.setItem('footballScoutApiBase', base);
  sessionStorage.setItem('footballScoutAccessCode', code);
  loadHistory();
});
$('#stop-polling').addEventListener('click', () => {
  clearTimeout(state.pollTimer);
  showToast('Suivi à l’écran arrêté. Le job n’a pas été relancé.', 'info');
});
$('#resume-job').addEventListener('click', () => openExistingJob(state.jobId));
if (state.jobId) $('#resume-job').hidden = false;
addEventListener('beforeunload', () => {
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.uploadController?.abort();
  clearTimeout(state.pollTimer);
});
