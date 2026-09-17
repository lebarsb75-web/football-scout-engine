# Analysis job lifecycle

The platform now separates a user-visible analysis job from the RunPod provider job ID.

## Why

The browser should never need to know the provider identifier or RunPod credentials. A platform-owned ID such as `ana_<uuid>` is returned instead and can later be tied to a user account, a match, billing records and generated assets.

## Current states

- `submitted`: provider accepted the job;
- `running`: provider reports `IN_PROGRESS`;
- `completed`: provider returned a structured engine result;
- `failed`: provider or result validation failed;
- `timed_out`: provider execution timed out;
- `cancelled`: provider execution was cancelled.

The API writes `submitted`, then refreshes only when an explicit client request calls the refresh endpoint. It does **not** run a background poller and never creates another paid execution while refreshing.

## Storage

Development uses SQLite through `api/jobs.py`.

Default path: `/tmp/football-scout-jobs.sqlite3`

Override with:

```bash
JOB_DB_PATH=/data/football-scout-jobs.sqlite3
```

SQLite is acceptable for the current single-instance prototype. Before public deployment, move this registry to a durable shared database (for example Postgres) so several API instances see the same jobs.

## Public API

`GET /analysis/jobs`

Returns recent locally known jobs.

`GET /analysis/jobs/{job_id}`

Returns one locally known job. This endpoint does not contact RunPod and cannot spend GPU credit.

The provider job ID is removed from public responses. It remains server-side only.

`POST /analysis/jobs/{job_id}/refresh`

Performs one read-only RunPod status request, stores a terminal result when present, and exposes it through the fail-closed quality contract. Provider IDs, raw engine output and provider diagnostics remain server-side.

## Next production step

Before public deployment, add a separate authenticated status synchronizer that:

1. receives a platform job ID;
2. loads the provider job ID server-side;
3. performs a read-only provider status request;
4. validates the result against a versioned response schema before storing it;
5. updates the local state;
6. exposes only `public_result(...)` to the browser;
7. records actual runtime/cost for benchmark calibration.

Do not add automatic retry of paid submissions without a durable idempotency mechanism.
