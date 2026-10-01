# Review evaluation

The 35 cases are synthetic, explicitly labeled changes. Expected labels are not
included in LLM input. Keep baseline results.json intact; save reruns separately.

From the project root in PowerShell, with backend dependencies installed:

```powershell
$env:PYTHONPATH = "backend"
python evaluation/evaluate.py --output evaluation/results-static-rerun.json
# Explicitly enables billed provider requests using local environment settings:
python evaluation/evaluate.py --live --output evaluation/results-live-rerun.json
```

For the existing Compose worker, whose environment contains provider settings:

```powershell
docker cp evaluation devflow-ai-worker-1:/evaluation
docker compose exec -T -e PYTHONPATH=/app --index 1 worker python /evaluation/evaluate.py --live --output /evaluation/results-rerun.json
docker cp devflow-ai-worker-1:/evaluation/results-rerun.json evaluation/results-rerun.json
```

Use the worker container name shown by `docker compose ps` if the project prefix
differs. Default execution is static-only; `--live` explicitly enables Gemini.
The first provider failure stops additional live calls. Results retain incomplete
statuses rather than assigning fabricated scores. No usage means unknown cost.

To include the evaluation scorer test in a backend-container test run:

```powershell
docker cp evaluation devflow-api:/evaluation
docker compose exec -T api pytest --cov=app --cov-report=term-missing
```

CI checks out both directories and needs no copy step. See
[methodology and results](../docs/ai-evaluation.md) for limitations.

## Separate provider latency run

After confirming provider availability and a call budget, run:

```powershell
$env:PYTHONPATH = "backend"
python evaluation/performance.py --live --count 10 --output evaluation/performance-results.json
```

This runner records successful median/P95 request latency, failure rate, and
provider-reported input/output/thinking tokens separately from infrastructure
throughput. It uses zero request retries. Cost remains null until dated pricing
for the configured model and all billed token categories is verified. It has not
been run as part of the zero-spend Vercel deployment; the last evaluation request
failed with HTTP 503. It measures provider calls, not end-to-end pipeline duration.
