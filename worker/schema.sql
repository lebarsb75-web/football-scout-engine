CREATE TABLE IF NOT EXISTS analysis_jobs (
    job_id TEXT PRIMARY KEY,
    provider_job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    cost_estimate_json TEXT NOT NULL,
    request_summary_json TEXT NOT NULL,
    video_key TEXT,
    result_json TEXT,
    provider_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_created_at
ON analysis_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS idempotency (
    idempotency_key TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    response_json TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_created_at
ON idempotency(created_at);
