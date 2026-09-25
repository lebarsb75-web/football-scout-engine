const PART_SIZE_BYTES = 90 * 1024 * 1024;
const DEFAULT_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024;
const DEFAULT_MAX_STORAGE_BYTES = 8 * 1024 * 1024 * 1024;
const UPLOAD_TTL_SECONDS = 2 * 60 * 60;
const DOWNLOAD_TTL_SECONDS = 24 * 60 * 60;
const VIDEO_RETENTION_HOURS = 24;
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'timed_out', 'cancelled']);
const ALLOWED_VIDEO_TYPES = new Set([
  'video/mp4',
  'video/quicktime',
  'video/webm',
  'video/x-m4v',
  'application/octet-stream',
]);

function corsHeaders(request, env) {
  const origin = request.headers.get('Origin') || '';
  const allowed = (env.ALLOWED_ORIGIN || '').split(',').map((item) => item.trim()).filter(Boolean);
  const headers = {
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,X-App-Access-Code,X-Idempotency-Key,X-Upload-Token',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
  if (allowed.includes(origin)) headers['Access-Control-Allow-Origin'] = origin;
  return headers;
}

function json(request, env, body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...corsHeaders(request, env),
      ...extraHeaders,
    },
  });
}

function fail(request, env, status, detail) {
  return json(request, env, { detail }, status);
}

async function readJson(request) {
  const contentType = request.headers.get('Content-Type') || '';
  if (!contentType.toLowerCase().includes('application/json')) throw new Error('JSON body required');
  return request.json();
}

function base64UrlEncode(value) {
  const bytes = value instanceof Uint8Array ? value : new TextEncoder().encode(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/g, '');
}

function base64UrlDecode(value) {
  const padded = value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - value.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function hmac(value, secret) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  return new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value)));
}

function constantTimeEqual(left, right) {
  const a = new TextEncoder().encode(left || '');
  const b = new TextEncoder().encode(right || '');
  let mismatch = a.length ^ b.length;
  const size = Math.max(a.length, b.length);
  for (let index = 0; index < size; index += 1) mismatch |= (a[index] || 0) ^ (b[index] || 0);
  return mismatch === 0;
}

export async function createToken(payload, secret) {
  const encoded = base64UrlEncode(JSON.stringify(payload));
  const signature = base64UrlEncode(await hmac(encoded, secret));
  return `${encoded}.${signature}`;
}

export async function verifyToken(token, secret, expectedScope, nowSeconds = Date.now() / 1000) {
  if (!token || !secret) throw new Error('Missing signed token');
  const [encoded, suppliedSignature, extra] = token.split('.');
  if (!encoded || !suppliedSignature || extra) throw new Error('Invalid signed token');
  const expectedSignature = base64UrlEncode(await hmac(encoded, secret));
  if (!constantTimeEqual(suppliedSignature, expectedSignature)) throw new Error('Invalid signed token');
  const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(encoded)));
  if (payload.scope !== expectedScope) throw new Error('Invalid token scope');
  if (!Number.isFinite(payload.exp) || payload.exp < nowSeconds) throw new Error('Signed token expired');
  return payload;
}

function requireAccess(request, env) {
  const provided = request.headers.get('X-App-Access-Code') || '';
  if (!env.APP_ACCESS_CODE || !constantTimeEqual(provided, env.APP_ACCESS_CODE)) {
    throw new Response(JSON.stringify({ detail: 'Code d’accès invalide.' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json', ...corsHeaders(request, env) },
    });
  }
}

function safeExtension(filename) {
  const extension = String(filename || '').toLowerCase().match(/\.(mp4|mov|m4v|webm)$/)?.[1];
  return extension || 'mp4';
}

function positiveNumber(value, fallback = null) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function storedVideoBytes(bucket) {
  let total = 0;
  let cursor;
  do {
    const page = await bucket.list({ prefix: 'uploads/', limit: 500, cursor });
    total += page.objects.reduce((sum, object) => sum + number(object.size), 0);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return total;
}

export function estimateCost(durationSeconds, env) {
  const duration = positiveNumber(durationSeconds);
  const price = positiveNumber(env.GPU_PRICE_PER_HOUR, 0.58);
  const benchmark = positiveNumber(env.BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE);
  if (!duration) throw new Error('video_duration_seconds must be > 0');
  if (!benchmark) {
    return {
      ready: false,
      reason: 'benchmark_required',
      message: 'Le test GPU court doit être validé avant toute analyse payante.',
    };
  }
  const estimatedGpuSeconds = duration / 60 * benchmark;
  const estimatedCost = estimatedGpuSeconds / 3600 * price;
  return {
    ready: true,
    gpu_price_per_hour_usd: Number(price.toFixed(4)),
    benchmark_gpu_seconds_per_video_minute: Number(benchmark.toFixed(3)),
    estimated_gpu_seconds: Number(estimatedGpuSeconds.toFixed(1)),
    estimated_cost_usd: Number(estimatedCost.toFixed(4)),
    recommended_max_authorization_usd: Number((estimatedCost * 1.35).toFixed(4)),
    safety_margin: 1.35,
  };
}

export function runpodBudgetPolicy(approvedMaxCostUsd, env) {
  const approved = positiveNumber(approvedMaxCostUsd);
  const price = positiveNumber(env.GPU_PRICE_PER_HOUR, 0.69);
  const hardCap = positiveNumber(env.MAX_JOB_COST_USD, 1);
  const idleSeconds = positiveNumber(env.RUNPOD_IDLE_TIMEOUT_SECONDS, 5);
  if (!approved || approved > hardCap) throw new Error('Le plafond autorisé dépasse la limite par analyse.');
  const totalBillableSeconds = approved / price * 3600;
  const executionSeconds = Math.max(1, Math.floor(totalBillableSeconds - idleSeconds));
  return {
    executionTimeout: executionSeconds * 1000,
    ttl: (executionSeconds + 600) * 1000,
  };
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function publicResult(engineResult) {
  if (!engineResult || engineResult.status !== 'completed') {
    return { status: 'unavailable', reason: 'engine_not_completed', metrics: {} };
  }
  const player = engineResult.player || {};
  const quality = engineResult.quality || {};
  const tracking = number(player.tracking_coverage_percent);
  const qualityScore = number(quality.score_percent);
  const playerQuality = number(quality.player_tracking_score_percent, qualityScore);
  const ballVisibility = number(quality.ball_visibility_percent);
  const calibrationUsed = Boolean(quality.pitch_calibration_used);
  const continuityOk = quality.tracking_continuity_reliable === true;
  const trackingOk = tracking >= 80 && playerQuality >= 82 && continuityOk;
  const ballOk = trackingOk && quality.ball_metrics_reliable === true && ballVisibility >= 40;
  const distanceAvailable = trackingOk && calibrationUsed && 'distance_meters_estimated' in player;
  const touchesAvailable = ballOk && 'ball_touches_estimated' in player;
  const possessionAvailable = ballOk && 'possession_seconds_estimated' in player;
  const clips = [];
  if (ballOk) {
    const rawClips = engineResult.clips || (player.touch_clip_windows_seconds || []).map((window) => ({
      type: 'touch', start: window[0], end: window[1],
    }));
    for (const clip of rawClips) {
      if (clip && ['touch', 'possession'].includes(clip.type)) {
        clips.push({ type: clip.type, start: number(clip.start), end: number(clip.end) });
      }
    }
  }
  return {
    status: trackingOk ? 'ready' : 'review_required',
    engine_version: engineResult.engine_version,
    quality: {
      score_percent: Number(qualityScore.toFixed(1)),
      player_tracking_score_percent: Number(playerQuality.toFixed(1)),
      tracking_coverage_percent: Number(tracking.toFixed(1)),
      ball_visibility_percent: Number(ballVisibility.toFixed(1)),
      tracking_continuity_reliable: continuityOk,
      tracking_pass: trackingOk,
      ball_metrics_pass: ballOk,
      pitch_calibration_used: calibrationUsed,
    },
    metrics: {
      tracking_coverage_percent: { available: true, value: Number(tracking.toFixed(1)), confidence: 'diagnostic' },
      distance_meters: distanceAvailable
        ? { available: true, value: Number(number(player.distance_meters_estimated).toFixed(1)), confidence: 'estimated' }
        : { available: false, reason: calibrationUsed ? 'tracking_quality_too_low' : 'pitch_calibration_required' },
      ball_touches: touchesAvailable
        ? { available: true, value: Math.trunc(number(player.ball_touches_estimated)), confidence: 'estimated' }
        : { available: false, reason: 'ball_or_tracking_quality_too_low' },
      possession_seconds: possessionAvailable
        ? { available: true, value: Number(number(player.possession_seconds_estimated).toFixed(1)), confidence: 'estimated' }
        : { available: false, reason: 'ball_or_tracking_quality_too_low' },
    },
    clips,
    notice: 'Les statistiques ne sont affichées que lorsque les contrôles qualité sont franchis.',
  };
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

async function fingerprint(value) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(value)));
  return base64UrlEncode(new Uint8Array(digest));
}

function validatePlayerProfile(value) {
  if (!value || typeof value !== 'object') return null;
  const name = String(value.name || '').trim().slice(0, 80);
  const position = String(value.position || '').trim().slice(0, 40);
  if (!name || !position) throw new Error('Le nom et le poste du joueur sont obligatoires.');
  const shirtNumber = value.shirt_number == null ? null : Number(value.shirt_number);
  if (shirtNumber != null && (!Number.isInteger(shirtNumber) || shirtNumber < 1 || shirtNumber > 99)) {
    throw new Error('Le numéro du joueur doit être compris entre 1 et 99.');
  }
  return {
    name,
    position,
    team: value.team ? String(value.team).trim().slice(0, 80) : null,
    shirt_number: shirtNumber,
  };
}

function validateMatchContext(value) {
  if (!value || typeof value !== 'object') return null;
  const date = value.match_date ? String(value.match_date) : null;
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error('Date de match invalide.');
  return {
    opponent: value.opponent ? String(value.opponent).trim().slice(0, 80) : null,
    match_date: date,
    source_filename: value.source_filename ? String(value.source_filename).trim().slice(0, 255) : null,
  };
}

async function createUpload(request, env) {
  requireAccess(request, env);
  const body = await readJson(request);
  const sizeBytes = positiveNumber(body.size_bytes);
  const maxBytes = positiveNumber(env.MAX_VIDEO_BYTES, DEFAULT_MAX_VIDEO_BYTES);
  const maxStorageBytes = positiveNumber(env.MAX_STORAGE_BYTES, DEFAULT_MAX_STORAGE_BYTES);
  const contentType = String(body.content_type || 'application/octet-stream').toLowerCase();
  if (!sizeBytes || sizeBytes > maxBytes) throw new Error(`La vidéo doit peser moins de ${Math.round(maxBytes / 1024 ** 3)} Go.`);
  const storedBytes = await storedVideoBytes(env.VIDEOS);
  if (storedBytes + sizeBytes > maxStorageBytes) {
    throw new Error('Plafond de stockage gratuit atteint. Attendez la suppression automatique des anciennes vidéos.');
  }
  if (!ALLOWED_VIDEO_TYPES.has(contentType)) throw new Error('Format vidéo non pris en charge.');
  const key = `uploads/${Date.now()}-${crypto.randomUUID()}.${safeExtension(body.filename)}`;
  const upload = await env.VIDEOS.createMultipartUpload(key, {
    httpMetadata: { contentType, cacheControl: 'private, no-store' },
    customMetadata: {
      originalName: String(body.filename || 'match').slice(0, 255),
      expectedSize: String(Math.trunc(sizeBytes)),
      createdAt: new Date().toISOString(),
    },
  });
  const token = await createToken({
    scope: 'upload',
    key,
    uploadId: upload.uploadId,
    size: Math.trunc(sizeBytes),
    exp: Math.floor(Date.now() / 1000) + UPLOAD_TTL_SECONDS,
  }, env.UPLOAD_SIGNING_SECRET);
  return json(request, env, {
    upload_id: upload.uploadId,
    upload_token: token,
    part_size_bytes: PART_SIZE_BYTES,
    expires_in_seconds: UPLOAD_TTL_SECONDS,
  }, 201);
}

async function uploadPart(request, env, uploadId, partNumber) {
  const token = await verifyToken(request.headers.get('X-Upload-Token'), env.UPLOAD_SIGNING_SECRET, 'upload');
  if (token.uploadId !== uploadId) throw new Error('Upload token mismatch');
  const maxPartNumber = Math.ceil(number(token.size) / PART_SIZE_BYTES);
  if (!Number.isInteger(partNumber) || partNumber < 1 || partNumber > maxPartNumber) throw new Error('Invalid part number');
  const contentLength = number(request.headers.get('Content-Length'));
  if (contentLength > PART_SIZE_BYTES) throw new Error('Video part is too large');
  const upload = env.VIDEOS.resumeMultipartUpload(token.key, token.uploadId);
  const part = await upload.uploadPart(partNumber, request.body);
  return json(request, env, { part_number: part.partNumber, etag: part.etag });
}

async function completeUpload(request, env, uploadId) {
  const token = await verifyToken(request.headers.get('X-Upload-Token'), env.UPLOAD_SIGNING_SECRET, 'upload');
  if (token.uploadId !== uploadId) throw new Error('Upload token mismatch');
  const existingObject = await env.VIDEOS.head(token.key);
  if (existingObject) return completedUploadResponse(request, env, token, existingObject, false);
  const body = await readJson(request);
  if (!Array.isArray(body.parts) || !body.parts.length) throw new Error('No uploaded parts supplied');
  const parts = body.parts.map((part) => ({
    partNumber: Number(part.part_number),
    etag: String(part.etag || ''),
  })).sort((left, right) => left.partNumber - right.partNumber);
  if (parts.some((part, index) => part.partNumber !== index + 1 || !part.etag)) throw new Error('Invalid uploaded parts');
  const upload = env.VIDEOS.resumeMultipartUpload(token.key, token.uploadId);
  const object = await upload.complete(parts);
  return completedUploadResponse(request, env, token, object, true);
}

async function completedUploadResponse(request, env, token, object, enforceStorageLimit) {
  if (token.size && object.size !== token.size) {
    await env.VIDEOS.delete(token.key);
    throw new Error('Uploaded video size does not match the selected file');
  }
  const maxStorageBytes = positiveNumber(env.MAX_STORAGE_BYTES, DEFAULT_MAX_STORAGE_BYTES);
  if (enforceStorageLimit && await storedVideoBytes(env.VIDEOS) > maxStorageBytes) {
    await env.VIDEOS.delete(token.key);
    throw new Error('Plafond de stockage gratuit atteint. La nouvelle vidéo a été supprimée.');
  }
  const downloadToken = await createToken({
    scope: 'download',
    key: token.key,
    exp: Math.floor(Date.now() / 1000) + DOWNLOAD_TTL_SECONDS,
  }, env.UPLOAD_SIGNING_SECRET);
  const origin = new URL(request.url).origin;
  return json(request, env, {
    uploaded: true,
    size_bytes: object.size,
    video_url: `${origin}/videos?token=${encodeURIComponent(downloadToken)}`,
    expires_in_seconds: DOWNLOAD_TTL_SECONDS,
  });
}

async function abortUpload(request, env, uploadId) {
  const token = await verifyToken(request.headers.get('X-Upload-Token'), env.UPLOAD_SIGNING_SECRET, 'upload');
  if (token.uploadId !== uploadId) throw new Error('Upload token mismatch');
  await env.VIDEOS.resumeMultipartUpload(token.key, token.uploadId).abort();
  return json(request, env, { aborted: true });
}

async function serveVideo(request, env, url) {
  const token = await verifyToken(url.searchParams.get('token'), env.UPLOAD_SIGNING_SECRET, 'download');
  const object = await env.VIDEOS.get(token.key, { range: request.headers });
  if (!object || !object.body) return fail(request, env, 404, 'Video unavailable');
  const headers = new Headers({
    'Cache-Control': 'private, no-store',
    'Accept-Ranges': 'bytes',
    ETag: object.httpEtag,
  });
  object.writeHttpMetadata(headers);
  let status = 200;
  if (object.range) {
    status = 206;
    const offset = object.range.offset || 0;
    const length = object.range.length || object.size;
    headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${object.size}`);
    headers.set('Content-Length', String(length));
  } else {
    headers.set('Content-Length', String(object.size));
  }
  return new Response(object.body, { status, headers });
}

function publicJob(row) {
  const result = row.result_json ? publicResult(JSON.parse(row.result_json)) : undefined;
  return {
    job_id: row.job_id,
    status: row.status,
    created_at: row.created_at,
    updated_at: row.updated_at,
    cost_estimate: JSON.parse(row.cost_estimate_json),
    request_summary: JSON.parse(row.request_summary_json),
    has_result: Boolean(row.result_json),
    has_error: Boolean(row.provider_error),
    ...(result ? { result } : {}),
  };
}

async function getJob(env, jobId) {
  return env.DB.prepare('SELECT * FROM analysis_jobs WHERE job_id = ?').bind(jobId).first();
}

async function listJobs(request, env) {
  requireAccess(request, env);
  const rows = await env.DB.prepare('SELECT * FROM analysis_jobs ORDER BY created_at DESC LIMIT 30').all();
  return json(request, env, { jobs: (rows.results || []).map(publicJob) });
}

async function showJob(request, env, jobId) {
  requireAccess(request, env);
  const row = await getJob(env, jobId);
  return row ? json(request, env, publicJob(row)) : fail(request, env, 404, 'Unknown analysis job');
}

async function submitAnalysis(request, env) {
  requireAccess(request, env);
  if (String(env.ENABLE_PAID_GPU).toLowerCase() !== 'true') {
    return fail(request, env, 423, 'Les analyses GPU sont verrouillées jusqu’à la validation du test court.');
  }
  if (!env.RUNPOD_API_KEY || !env.RUNPOD_ENDPOINT_ID) return fail(request, env, 503, 'RunPod is not configured');
  const idempotencyKey = request.headers.get('X-Idempotency-Key') || '';
  if (!/^[A-Za-z0-9._:-]{12,128}$/.test(idempotencyKey)) return fail(request, env, 400, 'X-Idempotency-Key is required');
  const body = await readJson(request);
  const duration = positiveNumber(body.video_duration_seconds);
  const targetTime = number(body.target_time_seconds, -1);
  const target = body.target || {};
  if (!duration || duration > 6 * 60 * 60 || targetTime < 0 || targetTime >= duration) throw new Error('Paramètres vidéo invalides.');
  if (![target.x, target.y].every((value) => Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 1)) {
    throw new Error('Position du joueur invalide.');
  }
  const videoUrl = new URL(String(body.video_url || ''));
  if (videoUrl.origin !== new URL(request.url).origin || videoUrl.pathname !== '/videos') throw new Error('La vidéo doit provenir du stockage privé Football Scout.');
  const downloadToken = await verifyToken(videoUrl.searchParams.get('token'), env.UPLOAD_SIGNING_SECRET, 'download');
  const estimate = estimateCost(duration, env);
  if (!estimate.ready) return fail(request, env, 412, estimate.message);
  const approved = positiveNumber(body.approved_max_cost_usd);
  const maxJobCost = positiveNumber(env.MAX_JOB_COST_USD, 1);
  if (!approved || approved > maxJobCost || approved < estimate.recommended_max_authorization_usd) {
    return fail(request, env, 412, `Le plafond autorisé doit couvrir l’estimation sans dépasser ${maxJobCost.toFixed(2)} $.`);
  }
  const providerPolicy = runpodBudgetPolicy(approved, env);
  const playerProfile = validatePlayerProfile(body.player_profile);
  const matchContext = validateMatchContext(body.match_context);
  const normalized = {
    video_url: videoUrl.toString(), duration, target_time_seconds: targetTime,
    target: { x: Number(target.x), y: Number(target.y) },
    sample_fps: Math.min(10, Math.max(1, number(body.sample_fps, 5))),
    confidence: Math.min(0.9, Math.max(0.1, number(body.confidence, 0.22))),
    image_size: Math.min(1280, Math.max(640, Math.trunc(number(body.image_size, 960)))),
    approved_max_cost_usd: approved,
    player_profile: playerProfile,
    match_context: matchContext,
  };
  const payloadFingerprint = await fingerprint(normalized);
  const existing = await env.DB.prepare('SELECT fingerprint, state, response_json FROM idempotency WHERE idempotency_key = ?').bind(idempotencyKey).first();
  if (existing) {
    if (existing.fingerprint !== payloadFingerprint) return fail(request, env, 409, 'Idempotency key reused with a different analysis');
    if (existing.state === 'completed' && existing.response_json) return json(request, env, { ...JSON.parse(existing.response_json), idempotent_replay: true });
    return fail(request, env, 409, 'Cette analyse est déjà en cours de soumission.');
  }
  const reservation = await env.DB.prepare(
    'INSERT OR IGNORE INTO idempotency (idempotency_key, fingerprint, state, created_at) VALUES (?, ?, ?, ?)',
  ).bind(idempotencyKey, payloadFingerprint, 'pending', Date.now() / 1000).run();
  if (!reservation.meta?.changes) return fail(request, env, 409, 'Cette analyse est déjà en cours de soumission.');
  const providerResponse = await fetch(`https://api.runpod.ai/v2/${env.RUNPOD_ENDPOINT_ID}/run`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.RUNPOD_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      input: {
        video_url: normalized.video_url,
        target: normalized.target,
        target_time_seconds: normalized.target_time_seconds,
        sample_fps: normalized.sample_fps,
        confidence: normalized.confidence,
        image_size: normalized.image_size,
      },
      policy: providerPolicy,
    }),
  });
  if (!providerResponse.ok) return fail(request, env, 502, 'RunPod n’a pas accepté la soumission. La clé reste réservée pour éviter un double envoi.');
  const providerBody = await providerResponse.json();
  const providerJobId = String(providerBody.id || providerBody.jobId || '');
  if (!providerJobId) return fail(request, env, 502, 'RunPod n’a retourné aucun identifiant de job.');
  const now = Date.now() / 1000;
  const jobId = `ana_${crypto.randomUUID().replaceAll('-', '')}`;
  const requestSummary = {
    video_duration_seconds: duration,
    target_time_seconds: targetTime,
    sample_fps: normalized.sample_fps,
    image_size: normalized.image_size,
    player_profile: playerProfile,
    match_context: matchContext,
  };
  const response = {
    submitted: true,
    idempotent_replay: false,
    job: {
      job_id: jobId, status: 'submitted', created_at: now, updated_at: now,
      cost_estimate: estimate, request_summary: requestSummary, has_result: false, has_error: false,
    },
    cost_estimate: estimate,
  };
  await env.DB.batch([
    env.DB.prepare('INSERT INTO analysis_jobs (job_id, provider_job_id, status, created_at, updated_at, cost_estimate_json, request_summary_json, video_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)')
      .bind(jobId, providerJobId, 'submitted', now, now, JSON.stringify(estimate), JSON.stringify(requestSummary), downloadToken.key),
    env.DB.prepare('UPDATE idempotency SET state = ?, response_json = ? WHERE idempotency_key = ?')
      .bind('completed', JSON.stringify(response), idempotencyKey),
  ]);
  return json(request, env, response, 201);
}

async function refreshJob(request, env, jobId, ctx) {
  requireAccess(request, env);
  const row = await getJob(env, jobId);
  if (!row) return fail(request, env, 404, 'Unknown analysis job');
  if (TERMINAL_STATUSES.has(row.status)) return json(request, env, publicJob(row));
  if (!env.RUNPOD_API_KEY || !env.RUNPOD_ENDPOINT_ID) return fail(request, env, 503, 'RunPod is not configured');
  const response = await fetch(`https://api.runpod.ai/v2/${env.RUNPOD_ENDPOINT_ID}/status/${row.provider_job_id}`, {
    headers: { Authorization: `Bearer ${env.RUNPOD_API_KEY}` },
  });
  if (!response.ok) return fail(request, env, 502, 'Impossible de récupérer le statut RunPod.');
  const provider = await response.json();
  const statuses = { IN_QUEUE: 'queued', IN_PROGRESS: 'running', COMPLETED: 'completed', FAILED: 'failed', TIMED_OUT: 'timed_out', CANCELLED: 'cancelled' };
  let status = statuses[String(provider.status || '').toUpperCase()] || 'unknown';
  let result = status === 'completed' && provider.output && typeof provider.output === 'object' ? provider.output : null;
  let providerError = ['failed', 'timed_out', 'cancelled'].includes(status) ? String(provider.error || status).slice(0, 1000) : null;
  if (status === 'completed' && !result) {
    status = 'failed';
    providerError = 'RunPod completed without a valid object result';
  }
  await env.DB.prepare('UPDATE analysis_jobs SET status = ?, updated_at = ?, result_json = ?, provider_error = ? WHERE job_id = ?')
    .bind(status, Date.now() / 1000, result ? JSON.stringify(result) : null, providerError, jobId).run();
  if (TERMINAL_STATUSES.has(status) && row.video_key) ctx.waitUntil(env.VIDEOS.delete(row.video_key));
  return json(request, env, publicJob(await getJob(env, jobId)));
}

async function cleanupOldVideos(env) {
  const cutoff = Date.now() - VIDEO_RETENTION_HOURS * 60 * 60 * 1000;
  let cursor;
  do {
    const page = await env.VIDEOS.list({ prefix: 'uploads/', limit: 500, cursor, include: ['customMetadata'] });
    const expired = page.objects.filter((object) => {
      const createdAt = Date.parse(object.customMetadata?.createdAt || '');
      return Number.isFinite(createdAt) && createdAt < cutoff;
    }).map((object) => object.key);
    if (expired.length) await env.VIDEOS.delete(expired);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
}

async function handle(request, env, ctx) {
  const url = new URL(request.url);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(request, env) });
  if (request.method === 'GET' && url.pathname === '/health') {
    return json(request, env, {
      status: 'ok',
      paid_gpu_enabled: String(env.ENABLE_PAID_GPU).toLowerCase() === 'true',
      runpod_configured: Boolean(env.RUNPOD_ENDPOINT_ID && env.RUNPOD_API_KEY),
      benchmark_available: Boolean(positiveNumber(env.BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE)),
      max_job_cost_usd: positiveNumber(env.MAX_JOB_COST_USD, 1),
      storage: 'r2_private_multipart',
      max_video_bytes: positiveNumber(env.MAX_VIDEO_BYTES, DEFAULT_MAX_VIDEO_BYTES),
      max_storage_bytes: positiveNumber(env.MAX_STORAGE_BYTES, DEFAULT_MAX_STORAGE_BYTES),
      video_retention_hours: VIDEO_RETENTION_HOURS,
      job_registry: 'd1_durable',
    });
  }
  if (request.method === 'GET' && url.pathname === '/videos') return serveVideo(request, env, url);
  if (request.method === 'POST' && url.pathname === '/uploads') return createUpload(request, env);
  const partMatch = url.pathname.match(/^\/uploads\/([^/]+)\/parts\/(\d+)$/);
  if (request.method === 'PUT' && partMatch) return uploadPart(request, env, decodeURIComponent(partMatch[1]), Number(partMatch[2]));
  const completeMatch = url.pathname.match(/^\/uploads\/([^/]+)\/complete$/);
  if (request.method === 'POST' && completeMatch) return completeUpload(request, env, decodeURIComponent(completeMatch[1]));
  const uploadMatch = url.pathname.match(/^\/uploads\/([^/]+)$/);
  if (request.method === 'DELETE' && uploadMatch) return abortUpload(request, env, decodeURIComponent(uploadMatch[1]));
  if (request.method === 'POST' && url.pathname === '/analysis/estimate') {
    requireAccess(request, env);
    const body = await readJson(request);
    return json(request, env, estimateCost(body.video_duration_seconds, env));
  }
  if (request.method === 'POST' && url.pathname === '/analysis/submit') return submitAnalysis(request, env);
  if (request.method === 'GET' && url.pathname === '/analysis/jobs') return listJobs(request, env);
  const refreshMatch = url.pathname.match(/^\/analysis\/jobs\/([^/]+)\/refresh$/);
  if (request.method === 'POST' && refreshMatch) return refreshJob(request, env, decodeURIComponent(refreshMatch[1]), ctx);
  const jobMatch = url.pathname.match(/^\/analysis\/jobs\/([^/]+)$/);
  if (request.method === 'GET' && jobMatch) return showJob(request, env, decodeURIComponent(jobMatch[1]));
  return fail(request, env, 404, 'Not found');
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await handle(request, env, ctx);
    } catch (error) {
      if (error instanceof Response) return error;
      return fail(request, env, 400, error instanceof Error ? error.message : 'Invalid request');
    }
  },
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(cleanupOldVideos(env));
  },
};
