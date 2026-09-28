# Engineering baseline ? 2026-09-28

## Scope and limitations

No live GitHub PR/LLM end-to-end result is claimed. The worker still has no App ID
or mounted private key. Earlier live Gemini requests returned provider errors.
The data below measures actual local executions, with external services explicitly
mocked where stated. Three samples are a baseline, not a throughput benchmark.
Docker Desktop/Windows was starting cold; image builds ran concurrently and may
have affected timing. No warm-up or outlier removal was performed.

## Signed PR integration baseline (external services mocked)

The same four-line Python fixture was reviewed three times under distinct synthetic
PR numbers to respect repo/PR/SHA idempotency. A signed webhook entered FastAPI;
PostgreSQL persisted jobs; an isolated Redis queue and Celery solo worker processed
them; real Ruff and Bandit ran; reports persisted; mocked GitHub accepted checks.
AI returned one fixed finding without an API request. Publication was retried for
each review and created no duplicate checks/annotations. Fixture rows were removed.

All durations below are seconds.

| Run | Webhook acknowledgment | Queue wait | Ruff + Bandit | Job creation ? report assembly | Workflow incl. mock check + retry |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.4007 | 0.1184 | 1.2053 | 1.3474 | 1.9801 |
| 2 | 0.0641 | 0.0343 | 1.0594 | 1.1460 | 1.2825 |
| 3 | 0.0345 | 0.0187 | 0.6683 | 0.7076 | 0.8383 |

Each run produced 2 static findings (1 Ruff, 1 Bandit) and 1 **mocked** AI finding.
`ai_analysis_seconds` in raw samples measures only the fake, not LLM latency.
Webhook timing uses FastAPI TestClient rather than an internet delivery. Queue wait
is created_at to started_at; report time ends just before its database commit.
Workflow timing includes polling and the duplicate-publication assertion.
Raw records: [benchmark-integration.json](benchmark-integration.json).

## Separate HTTP/component check

Three signed ping events were acknowledged over HTTP (not PR enqueue), and the same
Python fixture was passed to real Ruff/Bandit each time. Median HTTP round trip:
0.0189s; median static analysis: 0.5593s.

Cold first-request timing is retained in [benchmark-local.json](benchmark-local.json).

## Still unmeasured

| Metric | Live result |
| --- | --- |
| Internet webhook latency / live PR queue wait | Not measured |
| LLM duration | Not measured |
| PR receipt ? live Check Run completion | Not measured |
| LLM input/output/thinking tokens | Not measured, not zero |
| Estimated live review cost | Not calculated without successful usage and verified model pricing |

Successful Gemini responses now preserve usageMetadata counters in scope_summary.ai.usage.
Cost must be calculated from actual billed token categories and a dated provider
price reference; never infer token usage from input characters or mock timings.
The report stores queue, static, AI, job-to-report timings and separate source counts.
Server-Timing reports API handler duration including authentication and acknowledgment.

## Reproduce

```bash
docker compose up -d --build --scale worker=3
docker compose exec api python -m scripts.benchmark_local
docker compose exec api python -m scripts.local_pipeline_smoke
docker compose exec api pytest -q
docker build -f frontend/Dockerfile.test -t devflow-dashboard-tests frontend
docker run --rm --add-host=host.docker.internal:host-gateway devflow-dashboard-tests
```

Live gate: configure GitHub App ID/private key and accepted Checks write, Contents
read, Pull requests read permissions; route only the webhook path through a tunnel;
verify Gemini availability; open/update a dedicated test PR; save the job/check IDs,
report, component timings and token usage; repeat with distinct commit SHAs. Do not
reset production job identities to bypass deduplication.
