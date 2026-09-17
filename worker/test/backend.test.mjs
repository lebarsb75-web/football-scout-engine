import assert from 'node:assert/strict';
import test from 'node:test';

import worker, { canonicalJson, createToken, estimateCost, publicResult, verifyToken } from '../src/index.js';

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
