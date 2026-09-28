"""Signed webhook -> PostgreSQL -> Redis/Celery -> report -> mocked GitHub.
GitHub and AI are deterministic fakes. This is NOT live-provider verification.
"""
import hashlib, hmac, json, time
from uuid import uuid4
from unittest.mock import patch
from datetime import datetime, timezone
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, delete
from app.main import app
from app.config import settings
from app.db.session import SessionLocal
from app.models import ReviewJob, WebhookEvent
from app.workers.celery_app import celery_app
from app.schemas.changed_file import PullRequestSnapshot
from app.schemas.finding import CodeFinding

SOURCE = "import os\n\ndef run(command):\n    os.system(command)\n"
SHA = "a" * 40
RUN = str(uuid4())
QUEUE = "benchmark-" + RUN
SECRET = "local-benchmark-only"
checks, annotations = {}, {}

class GitHub:
    def __init__(self, *args): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get_pull_request(self,*args): return {"head":{"sha":SHA}}
    def get_review_snapshot(self,*args):
        return PullRequestSnapshot(github_repository_id=1,base_sha="b"*40,head_sha=SHA,files=[dict(
            filename="fixture.py",status="added",additions=4,deletions=0,changes=4,
            patch="@@ -0,0 +1,4 @@\n"+"\n".join("+"+line for line in SOURCE.splitlines()))])
    def get_file_content(self,*args): return SOURCE.encode()
    def list_check_runs(self,*args): return list(checks.values())
    def create_check_run(self,repo,**fields):
        number=len(checks)+1
        checks[number]={"id":number,**fields}
        annotations[number]=[]
        return checks[number]
    def update_check_run(self,repo,check_id,**fields):
        annotations[check_id].extend(fields.get("output",{}).get("annotations",[]))
        checks[check_id].update(fields)
    def list_check_annotations(self,repo,check_id): return annotations[check_id]

class AI:
    def analyze_files(self,*args):
        return [CodeFinding(file_path="fixture.py",line_number=4,source="ai",category="shell",severity="high",
            title="Synthetic AI fixture",description="This is a mocked response.",suggestion="Use argv.")], {
            "enabled":True,"skipped_files":[],"reviewed_files":["fixture.py"],"usage":[]}

results=[]
ids=[]
original_routes=celery_app.conf.task_routes
celery_app.conf.task_routes={"app.workers.review_tasks.process_review":{"queue":QUEUE},
                           "app.workers.publication_tasks.publish_review":{"queue":QUEUE}}
try:
 with patch.object(settings,"github_webhook_secret",SecretStr(SECRET)), patch.object(settings,"ai_enabled",True), patch.object(settings,"github_checks_enabled",True), patch("app.workers.review_tasks.GitHubService",GitHub), patch("app.workers.publication_tasks.GitHubService",GitHub), patch("app.workers.review_tasks.AIReviewer",AI):
  with start_worker(celery_app,pool="solo",queues=[QUEUE],perform_ping_check=False,shutdown_timeout=20), TestClient(app) as client:
   for run in range(3):
    payload={"action":"opened","repository":{"id":1,"full_name":"local-simulation/"+RUN},
      "installation":{"id":1},"pull_request":{"number":run+1,"head":{"sha":SHA},"base":{"sha":"b"*40}}}
    raw=json.dumps(payload).encode()
    start=time.perf_counter()
    response=client.post("/api/webhooks/github",content=raw,headers={"X-GitHub-Event":"pull_request",
      "X-GitHub-Delivery":str(uuid4()),"X-Hub-Signature-256":"sha256="+hmac.new(SECRET.encode(),raw,hashlib.sha256).hexdigest()})
    latency=time.perf_counter()-start
    assert response.status_code==202,response.text
    review_id=response.json()["review_id"]
    from uuid import UUID
    ids.append(UUID(review_id))
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
     with SessionLocal() as db:
      job=db.get(ReviewJob,UUID(review_id))
      if job.publication_status=="published": break
     time.sleep(.1)
    else: raise RuntimeError("publication timeout")
    report=client.get(f"/api/reviews/{review_id}/report").json()
    assert report["status"]=="completed"
    assert client.get("/api/reviews").status_code==200
    from app.workers.publication_tasks import publish_review
    publish_review.apply_async(args=[review_id],queue=QUEUE).get(timeout=20)
    assert len(checks)==run+1
    assert len(annotations[job.github_check_run_id])==report["summary"]["total_findings"]
    results.append({"run":run+1,"webhook_ack_seconds":latency,"workflow_through_check_seconds":time.perf_counter()-start,
      "report":report["measurements"],"findings":report["summary"],"duplicate_check_created":False})
finally:
 celery_app.conf.task_routes=original_routes
 with SessionLocal.begin() as db:
  db.execute(delete(WebhookEvent).where(WebhookEvent.review_id.in_(ids)))
  db.execute(delete(ReviewJob).where(ReviewJob.id.in_(ids)))
print(json.dumps({"recorded_at":datetime.now(timezone.utc).isoformat(),
 "kind":"isolated local integration: real Redis, Celery, PostgreSQL, Ruff, Bandit; MOCK GitHub and AI",
 "samples":results},indent=2))
