# DevFlow AI Architecture

## Current architecture — Day 2

The implemented backend accepts review-job requests through HTTP. GitHub pull
requests are the intended input, but GitHub App and webhook ingestion are planned.

```text
                         DEVFLOW AI

                         GitHub
                            │
                     Pull Request
                            │
                   (integration planned)
                            │
                            ▼
                   ┌─────────────────┐
                   │     FastAPI     │
                   │                 │
                   │ Review-job API  │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   PostgreSQL    │
                   │                 │
                   │   Review Jobs   │
                   └─────────────────┘
```

Docker Compose runs FastAPI, PostgreSQL, and Redis. Redis infrastructure is
available, but jobs are not yet enqueued or processed by workers. A `queued`
status is the initial persisted state, not evidence that a worker is running.

### API and persistence

| Method | Route | Implemented behavior |
| --- | --- | --- |
| GET | `/` | Service information |
| GET | `/health` | Database connectivity check and service status |
| POST | `/api/reviews` | Persist a review job; return HTTP 201 |
| GET | `/api/reviews/{review_id}` | Retrieve a persisted job; return 404 if missing |

The `review_jobs` table contains `id`, `repository_name`, `pull_request_number`,
`head_sha`, `status`, `attempt_count`, `created_at`, `started_at`, and `completed_at`.
The last two timestamps are nullable until processing starts or completes.
Allowed statuses are `queued`, `processing`, `completed`, `failed`, and
`superseded`, enforced by a database check constraint. No state machine is implemented.
SQLAlchemy models define
database representations; Pydantic schemas define API request and response data.

The database constraint `uq_review_commit` makes the combination of repository
name, pull-request number, and head SHA unique. Repeating the same POST returns
HTTP 409 with `Review already exists for this commit.` This prevents duplicate
job records; worker retries and external side-effect deduplication remain future work.

Alembic manages schema changes using `Base.metadata` and `settings.database_url`.
The initial migration creates `review_jobs`; application startup does not use
`Base.metadata.create_all()`.

PostgreSQL stores data in the Compose named volume `postgres_data`. A review was
created and retrieved, then retrieved unchanged after `docker compose down` and
`docker compose up -d`. Removing volumes with `down -v` would remove this data.

### Backend layout

- `app/api/`: HTTP routes.
- `app/db/`: SQLAlchemy base, engine, and database sessions.
- `app/models/`: database representations.
- `app/schemas/`: API request and response structures.
- `app/config.py`: application settings.
- `migrations/`: versioned Alembic schema changes.
- `tests/`: backend tests.

## Future Day 3+ architecture — planned

```text
                         GitHub
                            │
                         Webhook
                            ▼
                         FastAPI
                         │     │
                         │     └──── PostgreSQL
                         │
                         ▼
                        Redis
                         │
                         ▼
                    Celery Worker
                     │         │
                     ▼         ▼
                  Static    AI Review
                 Analysis      LLM
                     \         /
                      \       /
                       ▼     ▼
                       Findings
                          │
                          ▼
                    GitHub Checks
```

A GitHub App will receive signed webhook events through FastAPI. The backend
will persist review jobs in PostgreSQL and enqueue work through Redis. Celery
workers will retrieve changes, run static analysis and LLM review, and produce
findings for GitHub Check Runs.

Webhook validation, task dispatch, workers, static analysis, LLM review, and
GitHub Check publication are not implemented yet. PostgreSQL is intended to
remain the durable source of job state as retries and recovery are added.
