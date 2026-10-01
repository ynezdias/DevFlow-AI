"""Measure real HTTP/DB/queue/tool execution on the isolated benchmark stack."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import time
from uuid import uuid4
import httpx
from sqlalchemy import select
from app.config import settings
from app.db.session import SessionLocal
from app.models import ReviewJob, WebhookEvent


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, choices=[50, 100, 250], required=True)
    parser.add_argument("--workers", type=int, choices=[1, 2, 4], required=True)
    parser.add_argument("--duplicates", action="store_true")
    args = parser.parse_args()
    if settings.environment != "benchmark":
        raise RuntimeError("Refusing to load test a non-benchmark environment")
    run = str(uuid4())
    repository = "simulation/" + run
    secret = settings.github_webhook_secret.get_secret_value().encode()
    count = args.events
    duplicate_delivery = str(uuid4())
    with httpx.Client(base_url="http://api:8000", timeout=30) as client:
        ready_deadline = time.monotonic() + 60
        while True:
            try:
                if client.get("/health").json().get("database") == "healthy":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            if time.monotonic() > ready_deadline:
                raise RuntimeError("Benchmark API not ready after 60 seconds")
            time.sleep(.5)
        def send(index):
            body = json.dumps({"action": "opened", "repository": {"id": 1, "full_name": repository},
                "installation": {"id": 1}, "pull_request": {"number": 1 if args.duplicates else index + 1,
                    "head": {"sha": "a" * 40}, "base": {"sha": "b" * 40}}}).encode()
            headers = {"X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": duplicate_delivery if args.duplicates else str(uuid4()),
                "X-Hub-Signature-256": "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()}
            start = time.perf_counter()
            try:
                response = client.post("/api/webhooks/github", content=body, headers=headers)
                return {"seconds": time.perf_counter() - start, "http_status": response.status_code,
                    "status": response.json().get("status")}
            except httpx.HTTPError:
                return {"seconds": time.perf_counter() - start, "http_status": 0, "status": "transport_error"}
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            requests = list(pool.map(send, range(count)))
        deadline = time.monotonic() + 600
        expected = 1 if args.duplicates else count
        while True:
            with SessionLocal() as db:
                jobs = list(db.scalars(select(ReviewJob).where(ReviewJob.repository_name == repository)))
            terminal = [j for j in jobs if j.status in {"completed", "failed", "superseded"}]
            if len(terminal) == expected or time.monotonic() > deadline:
                break
            time.sleep(.2)
        elapsed = time.perf_counter() - start
    with SessionLocal() as db:
        delivery_rows = len(list(db.scalars(select(WebhookEvent).where(WebhookEvent.review_id.in_([j.id for j in jobs])))))
    samples = [{"id": str(j.id), "status": j.status, "attempts": j.attempt_count,
        "queue_wait_seconds": (j.started_at-j.created_at).total_seconds() if j.started_at else None,
        "processing_seconds": (j.completed_at-j.started_at).total_seconds() if j.completed_at and j.started_at else None,
        "measurements": ((j.scope_summary or {}).get("report") or {}).get("measurements")} for j in jobs]
    waits = [j["queue_wait_seconds"] for j in samples if j["queue_wait_seconds"] is not None]
    durations = [j["processing_seconds"] for j in samples if j["processing_seconds"] is not None]
    completed = sum(j.status == "completed" for j in jobs)
    output = dict(recorded_at=datetime.now(timezone.utc).isoformat(), run_id=run,
        kind="simulated workload; real HTTP/PostgreSQL/Redis/Celery/Ruff/Bandit; mock GitHub/AI; no publication",
        workers=args.workers, concurrency_per_worker=1, http_clients=10, events=count,
        duplicate_delivery_test=args.duplicates, elapsed_seconds=elapsed,
        webhook_p50_seconds=percentile([r["seconds"] for r in requests], .5),
        webhook_p95_seconds=percentile([r["seconds"] for r in requests], .95),
        queue_wait_p50_seconds=percentile(waits,.5), queue_wait_p95_seconds=percentile(waits,.95),
        processing_p50_seconds=percentile(durations,.5), processing_p95_seconds=percentile(durations,.95),
        completed=completed, failed=sum(j.status == "failed" for j in jobs),
        unfinished=len(jobs)-len(terminal), missing_jobs=max(0,expected-len(jobs)),
        logical_reviews=len(jobs), delivery_rows=delivery_rows, duplicate_jobs=max(0,len(jobs)-expected),
        http_statuses=dict(Counter(r["http_status"] for r in requests)),
        jobs_per_minute=completed / elapsed * 60, requests=requests, jobs=samples)
    name = f"load-{args.workers}w-{count}{'-duplicates' if args.duplicates else ''}.json"
    Path("/results", name).write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k:v for k,v in output.items() if k not in {"requests","jobs"}},indent=2))
    if completed != expected or output["duplicate_jobs"] or any(r["http_status"] not in {200,202} for r in requests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
