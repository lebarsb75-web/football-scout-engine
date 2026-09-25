import assert from 'node:assert/strict';
import test from 'node:test';

import worker, { canonicalJson, createToken, estimateCost, publicResult, runpodBudgetPolicy, verifyToken } from '../src/index.js';

test('cost estimate stays locked without a measured benchmark', () => {
  const result = estimateCost(26, { GPU_PRICE_PER_HOUR: '0.58', BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE: '0' });
  assert.equal(result.ready, false);
  assert.equal(result.reason, 'benchmark_required');
});

test('cost estimate matches the Python safety margin', () => {
  const result = estimateCost(120, { GPU_PRICE_PER_HOUR: '0.58', BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE: '30' });
  assert.equal(result.ready, true);
  assert.equal(result.estimated_gpu_seconds, 60);
  assert.equal(result.estimated_cost_usd, 0.0097);
  assert.equal(result.recommended_max_authorization_usd, 0.013);
});

test('RunPod execution policy cannot outspend the approved job budget', () => {
  const env = {
    GPU_PRICE_PER_HOUR: '0.69',
    MAX_JOB_COST_USD: '1.00',
    RUNPOD_IDLE_TIMEOUT_SECONDS: '5',
  };
  const policy = runpodBudgetPolicy(0.62, env);
  const maximumBillableCost = (policy.executionTimeout / 1000 + 5) / 3600 * 0.69;
  assert.ok(maximumBillableCost <= 0.62);
  assert.ok(policy.ttl > policy.executionTimeout);
  assert.throws(() => runpodBudgetPolicy(1.01, env), /limite par analyse/);
});

test('signed upload tokens enforce scope and expiry', async () => {
  const token = await createToken({ scope: 'upload', key: 'uploads/a.mp4', exp: 200 }, 'test-secret');
  const payload = await verifyToken(token, 'test-secret', 'upload', 100);
  assert.equal(payload.key, 'uploads/a.mp4');
  await assert.rejects(() => verifyToken(token, 'test-secret', 'download', 100), /scope/);
  await assert.rejects(() => verifyToken(token, 'test-secret', 'upload', 201), /expired/);
});

test('canonical JSON is stable across object key order', () => {
  assert.equal(canonicalJson({ b: 2, a: { y: 3, x: 1 } }), canonicalJson({ a: { x: 1, y: 3 }, b: 2 }));
});

test('public result exposes good tracking but hides unvalidated ball and distance metrics', () => {
  const result = publicResult({
    status: 'completed',
    engine_version: '2.4-dev',
    player: {
      tracking_coverage_percent: 97.3,
      distance_meters_estimated: 1234,
      ball_touches_estimated: 20,
    },
    quality: {
      score_percent: 95,
      player_tracking_score_percent: 96.5,
      tracking_continuity_reliable: true,
      ball_metrics_reliable: false,
      ball_visibility_percent: 9.2,
      pitch_calibration_used: false,
    },
  });
  assert.equal(result.status, 'ready');
  assert.equal(result.engine_version, '2.4-dev');
  assert.equal(result.metrics.distance_meters.available, false);
  assert.equal(result.metrics.ball_touches.available, false);
  assert.equal(result.metrics.possession_seconds.available, false);
});

test('public result fails closed when continuity verdict is missing', () => {
  const result = publicResult({
    status: 'completed',
    player: { tracking_coverage_percent: 99 },
    quality: { player_tracking_score_percent: 99 },
  });
  assert.equal(result.status, 'review_required');
  assert.equal(result.metrics.distance_meters.available, false);
});

test('worker health reveals readiness without exposing secrets', async () => {
  const request = new Request('https://api.example/health', { headers: { Origin: 'https://app.example' } });
  const response = await worker.fetch(request, {
    ALLOWED_ORIGIN: 'https://app.example',
    ENABLE_PAID_GPU: 'false',
    RUNPOD_ENDPOINT_ID: 'endpoint',
    RUNPOD_API_KEY: 'secret',
    BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE: '0',
  }, { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.paid_gpu_enabled, false);
  assert.equal(body.runpod_configured, true);
  assert.equal(body.benchmark_available, false);
  assert.equal(body.max_video_bytes, 4 * 1024 ** 3);
  assert.equal(body.max_storage_bytes, 8 * 1024 ** 3);
  assert.equal(body.video_retention_hours, 24);
  assert.equal(JSON.stringify(body).includes('secret'), false);
});

test('private estimate rejects a missing access code before any provider call', async () => {
  const request = new Request('https://api.example/analysis/estimate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: 'https://app.example' },
    body: JSON.stringify({ video_duration_seconds: 26 }),
  });
  const response = await worker.fetch(request, {
    ALLOWED_ORIGIN: 'https://app.example',
    APP_ACCESS_CODE: 'private-code',
  }, { waitUntil() {} });
  assert.equal(response.status, 401);
});

test('private estimate stays locked before the measured smoke benchmark', async () => {
  const request = new Request('https://api.example/analysis/estimate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-App-Access-Code': 'private-code',
      Origin: 'https://app.example',
    },
    body: JSON.stringify({ video_duration_seconds: 26 }),
  });
  const response = await worker.fetch(request, {
    ALLOWED_ORIGIN: 'https://app.example',
    APP_ACCESS_CODE: 'private-code',
    GPU_PRICE_PER_HOUR: '0.58',
    BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE: '0',
  }, { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.ready, false);
});

test('upload creation refuses to cross the private R2 storage ceiling', async () => {
  const request = new Request('https://api.example/uploads', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-App-Access-Code': 'private-code',
      Origin: 'https://app.example',
    },
    body: JSON.stringify({ filename: 'match.mp4', content_type: 'video/mp4', size_bytes: 2 * 1024 ** 3 }),
  });
  const response = await worker.fetch(request, {
    ALLOWED_ORIGIN: 'https://app.example',
    APP_ACCESS_CODE: 'private-code',
    UPLOAD_SIGNING_SECRET: 'signing-secret',
    MAX_VIDEO_BYTES: String(4 * 1024 ** 3),
    MAX_STORAGE_BYTES: String(8 * 1024 ** 3),
    VIDEOS: {
      async list() {
        return { objects: [{ key: 'uploads/old.mp4', size: 7 * 1024 ** 3 }], truncated: false };
      },
      async createMultipartUpload() {
        assert.fail('an over-budget upload must not be created');
      },
    },
  }, { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 400);
  assert.match(body.detail, /Plafond de stockage gratuit/);
});

test('upload completion can be retried after the object was already assembled', async () => {
  const uploadId = 'upload-123';
  const token = await createToken({
    scope: 'upload',
    key: 'uploads/retry.mp4',
    uploadId,
    size: 123,
    exp: Math.floor(Date.now() / 1000) + 60,
  }, 'signing-secret');
  const request = new Request(`https://api.example/uploads/${uploadId}/complete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Upload-Token': token,
      Origin: 'https://app.example',
    },
    body: JSON.stringify({ parts: [{ part_number: 1, etag: 'already-used' }] }),
  });
  const response = await worker.fetch(request, {
    ALLOWED_ORIGIN: 'https://app.example',
    UPLOAD_SIGNING_SECRET: 'signing-secret',
    VIDEOS: {
      async head(key) {
        assert.equal(key, 'uploads/retry.mp4');
        return { size: 123 };
      },
      async resumeMultipartUpload() {
        assert.fail('an already assembled object must not resume the multipart upload');
      },
    },
  }, { waitUntil() {} });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.uploaded, true);
  assert.equal(body.size_bytes, 123);
  assert.match(body.video_url, /^https:\/\/api\.example\/videos\?token=/);
});
