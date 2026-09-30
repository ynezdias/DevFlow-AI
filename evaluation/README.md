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
