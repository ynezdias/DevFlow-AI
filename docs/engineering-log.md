# Engineering log

This log records observed work and evidence, not hypothetical failures. Earlier
entries are reconstructed from this development session. Day numbers refer to
project milestones, not necessarily separate calendar days. Durations below are
local development observations, not production benchmarks.

## Days 1?2 ? Backend and persistence (2026-09-22)

Implemented:
- FastAPI review creation/retrieval and database health endpoint.
- PostgreSQL and Redis in Docker Compose; SQLAlchemy models and Alembic migrations.
- Unique review identity: repository name + PR number + head SHA.
- Queued/processing/completed/failed/superseded states and lifecycle timestamps.

Failures encountered:
- Docker commands failed because the Docker Desktop Linux engine was stopped.
  Starting Docker Desktop restored connectivity.
- Running Alembic against localhost returned a PostgreSQL authentication error.
  Running it inside Compose against `postgres` succeeded. The root cause of the
  host connection's authentication failure was not established.
- The running API image initially exposed only `/` and `/health`, despite review
  routes existing in source. Rebuilding loaded the current code.

Decisions:
- Use versioned migrations rather than application-startup `create_all()`.
- Keep models, schemas, routes, and database configuration separate.
- Keep `.env` ignored; track only `.env.example`.

Verification:
- POST returned 201; duplicate POST returned 409; GET matched persisted fields.
- After Compose down/up, all nine fields of review
  `c01d2f7a-bc3c-4b68-8c12-8f3a3cdd7960` were unchanged.
- PostgreSQL schema inspection confirmed the unique constraint.

## Day 3 ? Authenticated webhook ingestion (2026-09-22)

Implemented:
- HMAC-SHA256 verification over raw bytes before JSON parsing; constant-time comparison.
- Supported PR actions: opened, synchronize, reopened.
- Delivery uniqueness in `webhook_events` plus review commit uniqueness.
- Delivery recording and review creation in one database transaction.

Decisions:
- Invalid signatures return 401; ignored authenticated events are recorded.
- Use database uniqueness and conflict handling for concurrent requests.
- Preserve a retry opportunity by rolling back delivery recording if job creation fails.

Verification:
- 35 tests passed at this milestone, including failure rollback and retry.
- Four concurrent copies of a locally signed delivery produced one acceptance and
  three duplicates. A different delivery for the same commit reused the review ID.
- Opened [initial smoke PR #1](https://github.com/ynezdias/devflow-test-repo/pull/1).
  No actual GitHub webhook reached the API at that check. This was not a completed
  end-to-end GitHub delivery test.

## Day 4 ? Queue and workers (2026-09-22?23)

Implemented:
- Celery with Redis; webhook commit -> enqueue review UUID -> HTTP 202.
- Worker reads authoritative PostgreSQL state, initially simulates work, and saves completion.
- Pending delivery linkage permits explicit redelivery after queue publication failure.

Failures encountered:
- A missing newline when appending a dependency produced `httpxcelery[redis]` and
  failed the image build. Separating the dependency lines fixed it.
- A simulation edit missed a build's captured context. A source assertion inside
  the image caught the stale code. Rebuilding included the one-second simulation.
- A rebuild was temporarily blocked by the tool usage limit; it was completed on
  the next continuation.

Decisions:
- Commit before enqueueing to prevent a worker reading an uncommitted row. This
  was a preventative design decision; no missing-row race was observed here.
- Late acknowledgements do not guarantee exactly-once execution. The initial
  database-only worker skipped already completed jobs under a row lock.
- Remove the fixed worker container name to allow Compose scaling.

Measurements:
- 37 tests passed at the queue milestone.
- One live task recorded 1.01 seconds of simulated work, attempt_count=1; a repeat
  was skipped and left the row unchanged.
- Three containers, each with concurrency=2, processed 12 locally signed webhook
  jobs. All returned 202 and completed with one attempt. Logs showed four jobs per
  container; persisted timestamps showed six overlapping executions.
- Scope: local signed requests, not real GitHub-generated deliveries.

## Day 5 ? GitHub retrieval and scope controls (2026-09-23)

Implemented:
- GitHub service: App JWT -> installation token -> PR metadata and paginated files.
- Typed changed-file records, preserving filename/status/counts/patch.
- Persist installation/repository IDs, head/base SHA, selected files, and scope summary.
- Python-only scope: 20 files, 20,000 patch characters per file, 100,000 total.
- Skip unsupported, binary/missing-patch, generated, vendor, lock, removed, or
  over-limit files with explicit reasons. Never silently slice a patch.
- Temporary GitHub failures receive bounded retries; permanent failures are saved
  and raised. No Ruff, Bandit, or LLM analysis exists yet.

Decisions and limitations:
- Keep repository metadata denormalized until the end-to-end path is established.
- Release the DB transaction during GitHub calls. Processing is now committed
  before retrieval; a process crash can still strand a processing job.
- Compare head/base around pagination and mark changed snapshots superseded.
- Use `completed` plus `scope_summary.limited` for partial scope. Completion means
  retrieval/filtering, not a successful AI code review.
- Generated-file detection is heuristic. Missing/truncated GitHub patches cannot
  be assumed to represent the entire file.

Verification:
- 54 tests passed after App retrieval; 73 passed after scope and retry work.
- Tests use mocked GitHub responses and temporary test signing keys.
- Alembic schema consistency checks passed. Three workers and API are running;
  PostgreSQL and Redis health checks pass.
- Current credential-presence check: worker App ID absent; private-key file absent.
  Live App-authenticated diff retrieval remains blocked. Do not present fixture
  reads using developer credentials as verification of App authentication.

### Intentional-change PR experiment

Target repository: `ynezdias/devflow-test-repo`. Create separate fixtures for
`calculate_total`, `divide`, and `get_user`; inspect filename, line counts, patch,
and exact head SHA. Expected code behavior is not the test objective.

Failure encountered: pushing through the fresh checkout could not open Git's
username prompt (`failed to execute prompt script`, exit code 66). API access
worked. Retried Git with the existing credential in a process-local HTTP header,
without persisting it to the remote URL or a file.

### Verified fixture results ? 2026-09-23

| PR | File | Added / deleted | Head SHA |
| --- | --- | --- | --- |
| [#2](https://github.com/ynezdias/devflow-test-repo/pull/2) | `examples/calculate_total.py` | 2 / 0 | `b27a65443e1f6619e5f2547b5b77132131eb0082` |
| [#3](https://github.com/ynezdias/devflow-test-repo/pull/3) | `examples/divide.py` | 2 / 0 | `00f553cfc910e492368bf3b44f5aaf3cae7d16df` |
| [#4](https://github.com/ynezdias/devflow-test-repo/pull/4) | `examples/get_user.py` | 2 / 0 | `99a3373b1ee3da04abdbd48b95343d756e346c27` |

All three patches contain the exact intended two-line function. Each returned
`@@ -0,0 +1,2 @@`, and the API head SHA matched the pushed commit.
Full head/base SHAs and patches are recorded in [pr-fixtures.json](pr-fixtures.json).

This verifies the GitHub fixtures through REST using developer credentials only.
App-authenticated retrieval and signed delivery through DevFlow are still unverified.
After opening the PRs, API logs showed no incoming requests and PostgreSQL returned
zero review_jobs rows for this repository with PR numbers 2, 3, and 4.
No Ruff, Bandit, or LLM analysis was run.


## Daily entry template

### Day / date ? milestone

- Implemented:
- Failure observed (exact symptom; do not invent one):
- Evidence and root cause (separate confirmed facts from hypotheses):
- Fix:
- Design decision and trade-off:
- Verification and measurements (sample size, environment, observed results):
- Remaining limitations / next experiment:


## Day 6 prerequisite gate ? 2026-09-24

Per the requested sequence, static analysis has not started because live Day 5
App-authenticated retrieval is still unverified. Docker Desktop was stopped;
starting it and running Compose restored the API, three workers, PostgreSQL,
and Redis. `/health` reports healthy database connectivity.

Read-only checks from the running worker reported `app_id_configured=False` and
`private_key_exists=False`. PostgreSQL contains zero review jobs for
`ynezdias/devflow-test-repo`. Cloudflared is installed, but no tunnel process was
running. Needed next: App ID, local private-key PEM path, installation on the test
repository, and an active reachable webhook URL with the matching secret.
No Ruff/Bandit dependencies or analyzer code were added before this gate passes.
