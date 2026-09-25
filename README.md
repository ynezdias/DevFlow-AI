# DevFlow AI

**AI-Powered Pull Request Review Platform**

DevFlow AI is an automated code review platform designed to analyze GitHub pull requests using a combination of static analysis and Large Language Models (LLMs). The platform is being built to identify potential bugs, security vulnerabilities, and code-quality issues while providing developers with structured, actionable feedback directly within their GitHub workflow.

The project focuses not only on AI-powered code analysis, but also on building a reliable event-driven backend capable of handling asynchronous jobs, duplicate webhook events, retries, failures, and concurrent review processing.

> **Project Status:** 🚧 Currently under active development.

## Implementation Status

### Implemented

- [x] FastAPI backend
- [x] PostgreSQL persistence
- [x] Redis infrastructure
- [x] Review-job API
- [x] Signed PR webhook ingestion with delivery deduplication
- [x] Alembic migrations
- [x] Docker Compose
- [x] Celery worker scaffold (analysis not implemented)

The API creates and retrieves review jobs. Duplicate requests for the same
repository, pull-request number, and head SHA return HTTP 409. Persistence has
been verified across a Compose restart. Redis is running as infrastructure;
Celery runs a database-only worker scaffold; code analysis is not implemented yet.

### Planned

- [ ] GitHub App deployment and verified real deliveries
- [ ] Static analysis
- [ ] AI reviewer
- [ ] GitHub Check Runs

See [the architecture document](docs/architecture.md) for current behavior and
the planned Day 3+ workflow.

---

## 🎯 Project Goals

DevFlow AI is being built to explore the intersection of **software engineering, distributed systems, and applied AI**.

The platform aims to:

* Automatically analyze GitHub pull requests.
* Detect potential correctness and security issues.
* Run static analysis using tools such as Ruff and Bandit.
* Use an LLM to perform contextual code review.
* Generate structured and actionable review findings.
* Publish review results through GitHub Check Runs.
* Process reviews asynchronously using background workers.
* Handle duplicate events and failed jobs safely.
* Measure review latency, throughput, AI quality, and system reliability.

---

## ⚙️ Planned Workflow

```text
Developer opens/updates Pull Request
                │
                ▼
         GitHub Webhook
                │
                ▼
        FastAPI Backend
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
   PostgreSQL       Redis Queue
                         │
                         ▼
                   Celery Worker
                         │
                ┌────────┴────────┐
                ▼                 ▼
          Static Analysis     AI Analysis
          Ruff + Bandit          LLM
                │                 │
                └────────┬────────┘
                         ▼
                  Report Aggregator
                         │
                  ┌──────┴──────┐
                  ▼             ▼
             PostgreSQL    GitHub Check Run
                  │
                  ▼
            React Dashboard
```

### Planned Review Lifecycle

1. A developer opens or updates a pull request.
2. GitHub sends a signed webhook event to DevFlow AI.
3. The FastAPI backend validates the webhook and creates a review job.
4. The review job is persisted in PostgreSQL and submitted for asynchronous processing.
5. A Celery worker retrieves the pull-request changes.
6. Ruff and Bandit perform static analysis.
7. An LLM analyzes the changed code for additional issues.
8. Findings are validated, normalized, and deduplicated.
9. Results are stored in PostgreSQL.
10. DevFlow AI publishes the review through GitHub Checks.
11. Review history and metrics can be inspected through the dashboard.

---

## 🛠️ Tech Stack

The backend uses Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL, with
Docker Compose and Redis infrastructure. The stack below also includes planned
tools; Celery, AI analysis, frontend, and GitHub integrations are future work.

### Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* PostgreSQL

### Asynchronous Processing

* Redis
* Celery

### AI & Code Analysis

* LLM API
* Ruff
* Bandit
* Pydantic structured-output validation

### Frontend

* React
* TypeScript
* Vite

### Infrastructure

* Docker
* Docker Compose
* GitHub Actions

### Testing & Performance

* Pytest
* HTTPX
* Locust

### External Integration

* GitHub Apps
* GitHub REST API
* GitHub Webhooks
* GitHub Checks API

---

## 🔌 Implemented API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Service information |
| `GET` | `/health` | Service and PostgreSQL connectivity status |
| `POST` | `/api/reviews` | Create a review job; reject duplicates with HTTP 409 |
| `GET` | `/api/reviews/{review_id}` | Retrieve a persisted review job |

Interactive API documentation: [Swagger UI](http://localhost:8000/docs).

## Planned API Additions

| Method | Endpoint                   | Description                                |
| ------ | -------------------------- | ------------------------------------------ |
| `POST` | `/api/webhooks/github`     | Implemented: authenticate, deduplicate, and persist PR review jobs |
| `GET`  | `/api/repositories`        | List connected repositories                |
| `GET`  | `/api/reviews`             | List pull-request reviews                  |
| `GET`  | `/api/reviews/{id}`        | Extend existing job retrieval with findings |
| `GET`  | `/api/reviews/{id}/status` | Retrieve review-processing status          |
| `POST` | `/api/reviews/{id}/retry`  | Retry an eligible failed review            |
| `GET`  | `/api/metrics/summary`     | Retrieve processing metrics                |

---

## 🤖 Planned AI Review Pipeline

The AI reviewer is designed around structured and verifiable outputs rather than unrestricted natural-language responses.

```text
Pull Request Diff
        │
        ▼
Input Preparation
        │
        ├── Diff size limits
        ├── File filtering
        └── Secret redaction
        │
        ▼
Static Analysis
Ruff + Bandit
        │
        ▼
LLM Code Analysis
        │
        ▼
Pydantic Validation
        │
        ├── Validate file paths
        ├── Validate line numbers
        └── Validate response schema
        │
        ▼
Finding Normalization
        │
        ▼
Deduplication
        │
        ▼
Final Review Report
```

Repository content is treated as **untrusted input**. AI-generated output will be validated before findings can be published.

The LLM is used as an advisory reviewer and is not permitted to execute commands, access application secrets, modify repositories, or automatically merge pull requests.

---

## 🔒 Reliability & Security

DevFlow AI is being designed around several important reliability principles.

### Idempotent Processing

GitHub may deliver the same webhook multiple times once webhook ingestion is added. Review jobs already use a database unique constraint based on:

```text
repository + pull request number + head commit SHA
```

This prevents duplicate job records for the same commit. The API returns HTTP 409 for duplicates. Worker retries and deduplication of external side effects are planned.

### Commit-Aware Reviews

Every review is associated with an exact Git commit SHA.

Before publishing findings, DevFlow AI will verify that the pull request still references that commit. Reviews for outdated commits can therefore be marked as superseded instead of being presented as current results.

### Failure Recovery

Background jobs will support:

* bounded retries
* exponential backoff
* terminal failure states
* stale-job detection
* worker failure recovery

PostgreSQL acts as the durable source of review-job state instead of relying solely on the Redis queue.

### Secure Code Analysis

The initial version will **not execute arbitrary repository code or install repository dependencies**.

Static analysis will operate on retrieved source files without running untrusted project scripts.

---

## 🧪 Testing Strategy

The project will include several levels of testing:

### Unit Tests

Testing individual components such as:

* webhook signature validation
* job creation
* duplicate detection
* job state transitions
* AI response parsing
* finding validation
* retry logic

### Integration Tests

Testing interactions between:

```text
FastAPI ↔ PostgreSQL ↔ Redis ↔ Celery
```

### Reliability Tests

Failure scenarios will include:

* duplicate GitHub webhook deliveries
* concurrent workers
* worker crashes
* Redis interruptions
* malformed LLM responses
* GitHub API rate limiting
* stale pull-request commits

### AI Evaluation

A labeled dataset of Python code changes will be used to evaluate AI review quality using:

* Precision
* Recall
* False-positive rate

The LLM-based reviewer will also be compared with static analysis alone.

---

## 📊 Performance Goals

The following values are **development targets and not measured results**:

| Metric                    |    Initial Target |
| ------------------------- | ----------------: |
| Webhook API P95 latency   |        `< 500 ms` |
| Load-test queue           | `100 review jobs` |
| Duplicate logical reviews |               `0` |
| AI evaluation dataset     |    `50+ examples` |
| Backend test coverage     |            `80%+` |

Actual benchmark results will be documented after implementation and reproducible testing.

---

## 🗺️ Development Roadmap

### Phase 1 — Backend & GitHub Integration

* [x] Initialize FastAPI backend
* [x] Configure PostgreSQL
* [x] Configure Redis infrastructure
* [x] Add SQLAlchemy models
* [x] Add Alembic migrations
* [ ] Create GitHub App
* [x] Verify webhook signatures
* [x] Implement review-job creation API
* [ ] Add Celery workers
* [ ] Retrieve pull-request diffs
* [ ] Integrate Ruff and Bandit

### Phase 2 — AI Review Engine

* [ ] Integrate LLM provider
* [ ] Implement structured review prompts
* [ ] Validate responses with Pydantic
* [ ] Validate file and line references
* [ ] Normalize findings
* [ ] Deduplicate findings
* [ ] Publish GitHub Check Runs
* [ ] Build React dashboard

### Phase 3 — Reliability & Evaluation

* [ ] Implement retry and recovery mechanisms
* [ ] Add unit tests
* [ ] Add integration tests
* [ ] Add reliability tests
* [ ] Build AI evaluation dataset
* [ ] Benchmark AI review quality
* [ ] Run load tests
* [ ] Add CI/CD
* [ ] Deploy application
* [ ] Document benchmark results

---

## 🚧 Current Status

DevFlow AI is currently under development.

The Day 2 backend supports this implemented flow:

```text
HTTP client / Swagger UI
      ↓
FastAPI review-job API
      ↓
PostgreSQL
```

Signed PR webhook ingestion, Celery processing, PostgreSQL persistence, and static
analysis are implemented. Gemini AI review is implemented; GitHub Check publishing is implemented; live App verification requires credentials.
Live GitHub App delivery still requires credentials and a reachable webhook URL.

---

## 📈 Future Improvements

Potential future extensions include:

* JavaScript and TypeScript repository support
* Java repository support
* repository-specific review policies
* multi-provider LLM support
* retrieval of additional repository context
* developer feedback loops for AI findings
* calibrated finding confidence
* advanced observability and tracing
* isolated sandbox environments for automated test execution

---


## ⚠️ Disclaimer

DevFlow AI is an experimental developer tool. AI-generated code-review findings may contain false positives or miss issues and should not replace human code review or established security practices.

Webhook ingestion now supports opened, synchronize, and reopened PR events.
Delivery IDs and review commit identities provide two database deduplication layers.
A real GitHub delivery requires the App installation and public webhook URL to be configured.

Celery queue foundation: supported webhooks now persist, enqueue, and return HTTP 202.
Workers retrieve full Python source at the review head SHA and run Ruff and Bandit. Gemini review runs when `AI_ENABLED=true`.
See [architecture](docs/architecture.md#celery-queue-foundation) for delivery recovery limits.

GitHub App service and worker changed-file retrieval are implemented. Configure
`GITHUB_APP_ID` and the ignored `.secrets/github-app.pem` before live use. Review
responses expose persisted `changed_files` (including patches) and safe error codes.
Completion means scoped static analysis, optional Gemini review, and persisted findings. Read them with
`GET /api/reviews/{review_id}/findings`. Only findings starting on added diff lines are returned.


Review scope defaults: 20 Python files, 20,000 patch characters per file, and
100,000 total patch characters. Configure `MAX_FILES`,
`MAX_PATCH_CHARS_PER_FILE`, and `MAX_TOTAL_PATCH_CHARS` in `.env`, then recreate
workers. Review responses include typed selected files, repository/base metadata,
and `scope_summary` with every skipped filename and reason. Temporary GitHub
failures receive bounded retries.

Development evidence: [Engineering log](docs/engineering-log.md) records observed
failures, design decisions, measurements, and intentional PR fixtures.


## Gemini reviewer

Set `AI_ENABLED=true`, `AI_PROVIDER=gemini`, `AI_MODEL=gemini-3.8-flash`, and
`GEMINI_API_KEY` in the ignored local `.env`. Recreate workers after changing them.
The key is passed only to workers, never baked into images. Do not put secret
values in `.gitignore`; it contains filename patterns, not credentials.

The reviewer uses Gemini REST through the existing httpx dependency. Code and
diffs are sent as untrusted user data, separate from fixed system instructions.
Returned findings must validate against the common schema, reference the supplied
file, and start on an added diff line. AI and static findings persist together.
Component failures mark the review failed with a safe error code while preserving successful analysis results.

Defaults: 20 files, 20,000 diff characters per file, 100,000 serialized input
characters per review (including prompt/schema and retry budget), 4,096 output
tokens per request, 30-second HTTP operation timeout, and one retry for transient
errors. These are size controls, not a guaranteed dollar budget. Context is the
full head file; oversized files are skipped whole, with reasons in `scope_summary.ai`.
There is no silent context truncation. Findings are available through the existing
findings endpoint. AI can produce false positives; publishing and report deduplication
are future work.


## Validated review reports

`GET /api/reviews/{review_id}/report` returns the persisted combined report for
newly completed jobs. It contains severity counts, validated findings, analysis
status, original normalized tool findings, merge provenance, and rejection reasons.
Missing reviews return 404; unfinished jobs and legacy jobs without a validated
report return 409 rather than an invented empty report.

Validation rejects unsupported severities, malformed fields, unknown paths, invalid
line numbers, descriptions over 4,000 characters, and findings outside added diff
lines. Locations are checked against the exact head source fetched by the worker.
Unified diff parsing checks hunk lengths and tracks old/new positions. Truncated
or overlapping hunks fail closed.

Deduplication uses exact `(file_path, line_number, category)` matches. The highest
severity is retained with deterministic tie-breaking; all original normalized
findings and their indices remain in the report. Different categories on one line
remain separate. Rule IDs are not guessed to be equivalent to broad AI categories.
Use report findings for future publication, not the raw `/findings` audit endpoint.

Reports are committed with findings and completion in the existing JSONB
`scope_summary.report`; no database schema migration is needed. AI analysis is
reported as disabled, limited, or completed. A failed component marks the job and report failed; successful results remain available. Location/schema validation cannot prove an AI
claim is semantically correct.


### Partial analysis failures

Static and AI analysis run independently after source retrieval. If either fails,
the job and persisted report have `status=failed` and the job has
`error_code=analysis_incomplete`. The report records each component as completed,
failed, disabled, or limited. Successful findings are retained, including findings
from AI files reviewed before another file fails. Both-component failure produces
a failed report with zero findings, not a clean review.

`GET /api/reviews/{id}/report` serves these partial reports. Failures during GitHub
retrieval still follow the existing retry/error path because there is no source
to analyze. Duplicate task delivery skips terminal failed jobs; component-level
resumption is not implemented. Raw exception/provider text is not exposed.

Model output wrapped in Markdown fences is rejected as invalid JSON. Markdown,
HTML, and instruction-like text inside valid finding fields remain inert JSON
strings for audit; consumers must render them as plain text, not trusted HTML or
commands. No publishing or HTML renderer exists yet. Schema validation does not
claim to detect every malicious sentence or establish factual correctness.


## GitHub Check Runs

Enable `GITHUB_CHECKS_ENABLED=true` on workers (Compose default). Configure the
App ID and mounted private-key PEM, install the App on the test repository, and
grant **Checks: read/write**, **Contents: read**, **Pull requests: read**. Accept
updated permissions on the installation after editing the App configuration.
Authentication uses the existing App installation-token service, never a PAT.

Workers create an in-progress **DevFlow AI Code Review** on the stored head SHA.
After committing the report, a separate publication task updates that check.
The API exposes `github_check_run_id` and `publication_status`. Publication errors
do not erase analysis results or change analysis success into an analysis failure.

Conclusion policy: clean complete reviews use success; advisory findings, disabled
AI, or limited scope use neutral; failed analysis uses action_required. Findings
use notice/warning annotations, never failure solely for an AI severity. Summary
counts come from validated report findings, not model-written summary prose.

The publisher revalidates changed-line locations and sends at most 50 annotations
per request. It checks the current PR head before creation, each annotation batch,
and completion. A moved head marks the job superseded and cancels the old check.
Annotations already sent remain attached only to the old SHA. A head can still
change immediately after the final read; GitHub provides no atomic compare-and-publish.

A PostgreSQL row lock serializes local publishers. The persisted check ID is reused.
If a create response was lost, external_id matching against the App's checks
recovers the remote ID. Annotation fingerprints in raw_details reconcile accepted
batches before retrying. This handles normal redelivery and observed remote state;
GitHub has no create idempotency key, so this is not a distributed exactly-once
guarantee during ambiguous failures or delayed remote visibility.

Transient publication failures retry up to three times. To retry publication from
the stored report without re-running analysis:

```bash
docker compose exec worker celery -A app.workers.celery_app:celery_app call app.workers.publication_tasks.publish_review --args='["REVIEW_UUID"]'
```

The commit-to-queue crash gap has no automatic outbox recovery yet. Use the retry
command for enqueue_failed or interrupted publication; inspect publication_status.

Live acceptance: open/update a test PR, inspect the stored review/report, verify
the check's SHA and annotations, retry publication, and confirm the same check ID.
This remains unverified locally while the App ID and private-key mount are absent.
API permissions cannot be confirmed without those credentials.

API reference: [GitHub Check Runs](https://docs.github.com/en/rest/checks/runs).
