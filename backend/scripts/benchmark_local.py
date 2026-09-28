"""Local component baseline only; no GitHub or LLM requests are made."""
import hashlib
import hmac
import json
from time import perf_counter
from uuid import uuid4
from datetime import datetime, timezone
import httpx
from app.config import settings
from app.schemas.finding import AnalysisFile
from app.services.static_analyzer import StaticAnalyzer

source = "import os\n\ndef run_command(command):\n    os.system(command)\n"
file = AnalysisFile(filename="benchmark.py", content=source.encode(),
    patch="@@ -0,0 +1,4 @@\n" + "\n".join("+"+line for line in source.splitlines()))
results = []
with httpx.Client(base_url="http://localhost:8000", timeout=30) as client:
    for run in range(3):
        body = b'{"zen":"devflow local benchmark"}'
        secret = settings.github_webhook_secret.get_secret_value()
        headers = {"X-GitHub-Delivery": str(uuid4()), "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": "sha256="+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()}
        start=perf_counter()
        response=client.post("/api/webhooks/github",content=body,headers=headers)
        elapsed=perf_counter()-start
        start=perf_counter()
        findings=StaticAnalyzer().analyze([file])
        duration=perf_counter()-start
        results.append({"run":run+1,"webhook_kind":"signed ping (not PR enqueue)",
            "webhook_http_status":response.status_code,"webhook_roundtrip_seconds":elapsed,
            "server_timing":response.headers.get("server-timing"),
            "static_analysis_seconds":duration,"static_findings":len(findings),
            "static_by_source":{tool:sum(f.source==tool for f in findings) for tool in ("ruff","bandit")},
            "queue_wait_seconds":None,"ai_analysis_seconds":None,"ai_findings":None,
            "llm_input_tokens":None,"llm_output_tokens":None,"estimated_cost_usd":None,
            "end_to_end_seconds":None})
print(json.dumps({"recorded_at":datetime.now(timezone.utc).isoformat(),
    "kind":"local component baseline; no live PR, Redis, GitHub publication, or LLM",
    "fixture_sha256":hashlib.sha256(source.encode()).hexdigest(),"samples":results},indent=2))
