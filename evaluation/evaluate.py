"""Frozen synthetic benchmark. Run with backend on PYTHONPATH; --live opts into API calls."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from collections import Counter
from app.schemas.finding import AnalysisFile
from app.services.static_analyzer import StaticAnalyzer
from app.services.ai_reviewer import AIReviewer, AIReviewError
from app.config import settings

ROOT = Path(__file__).parent


def normalize(finding):
    result = finding.model_dump() if hasattr(finding, "model_dump") else dict(finding)
    category = result["category"]
    # Explicit fixed mapping, established before measuring. No title/keyword guessing.
    if result["source"] == "bandit":
        category = {"B110":"correctness", "B112":"correctness"}.get(category, "security")
    elif result["source"] == "ruff":
        category = "quality" if category in {"F401", "F841"} else "correctness"
    result["category"] = category
    return result


def score(expected, findings):
    remaining = Counter((x["file"], x["line"], x["category"]) for x in expected)
    tp = fp = 0
    for finding in findings:
        key = (finding["file_path"], finding["line_number"], finding["category"])
        if remaining[key]:
            tp += 1
            remaining[key] -= 1
        else:
            fp += 1
    fn = sum(remaining.values())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def deduplicate(findings):
    seen = set()
    result = []
    for item in findings:
        key = (item["file_path"], item["line_number"], item["category"])
        if key not in seen:
            result.append(item); seen.add(key)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "results.json")
    args = parser.parse_args()
    rows = []; digest = hashlib.sha256(); blocked = None
    config = settings.model_copy(update={"ai_max_retries":0, "ai_max_output_tokens":2048})
    for folder in sorted((ROOT / "dataset").glob("case_*")):
        meta=json.loads((folder/"labels.json").read_text())
        content=(folder/"after.py").read_bytes(); patch=(folder/"patch.diff").read_text()
        for name in ("before.py","after.py","patch.diff","labels.json"):
            digest.update((folder/name).read_bytes())
        source=AnalysisFile(filename=meta["file"],content=content,patch=patch)
        start=time.perf_counter()
        static=[normalize(f) for f in StaticAnalyzer().analyze([source])]
        row={"case_id":meta["case_id"],"expected":meta["expected"],
             "A":{"status":"completed","seconds":time.perf_counter()-start,"findings":static,"score":score(meta["expected"],static)}}
        for experiment in ("B", "ungrounded"):
            if not args.live or blocked:
                row[experiment]={"status":"not_run", "reason":blocked or "live_not_requested"}
                continue
            reviewer=AIReviewer(config)
            given_patch=patch if experiment=="B" else "@@ -0,0 +1,%d @@\n" % len(content.splitlines()) + "\n".join("+"+s for s in content.decode().splitlines())
            start=time.perf_counter()
            try:
                findings=[normalize(f) for f in reviewer.analyze("evaluation/"+meta["case_id"],meta["file"],given_patch,content.decode())]
                row[experiment]={"status":"completed","seconds":time.perf_counter()-start,"findings":findings,
                    "score":score(meta["expected"],findings),"usage":reviewer.usage,"estimated_cost_usd":None}
            except AIReviewError as exc:
                blocked=str(exc)
                row[experiment]={"status":"failed","error":blocked,"seconds":time.perf_counter()-start,"usage":reviewer.usage}
        if row["B"]["status"]=="completed":
            combined=deduplicate(static+row["B"]["findings"])
            row["C"]={"status":"completed","findings":combined,"score":score(meta["expected"],combined)}
        else: row["C"]={"status":"not_run","reason":"requires_successful_B"}
        rows.append(row)
    summaries={}
    for experiment in ("A","B","C","ungrounded"):
        completed=[r for r in rows if r[experiment]["status"]=="completed"]
        expected=[e for r in completed for e in [{**e,"file":r["case_id"]+":"+e["file"]} for e in r["expected"]]]
        findings=[{**f,"file_path":r["case_id"]+":"+f["file_path"]} for r in completed for f in r[experiment]["findings"]]
        summaries[experiment]={"completed_cases":len(completed),"total_cases":len(rows),
            "metrics":score(expected,findings) if completed else None}
    output={"dataset_sha256":digest.hexdigest(),"model":config.ai_model,"live_requested":args.live,
        "matching":"exact normalized category, path, new-file line; one-to-one",
        "summaries":summaries,"cases":rows}
    args.output.write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(summaries,indent=2))

if __name__ == "__main__": main()
