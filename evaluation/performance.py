"""Separate real-provider latency/usage benchmark; requires explicit --live."""
import argparse
import json
import math
from pathlib import Path
import statistics
import time
from datetime import datetime, timezone
from app.config import settings
from app.services.ai_reviewer import AIReviewer, AIReviewError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--count', type=int, choices=range(10,21), default=10)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'performance-results.json')
    args = parser.parse_args()
    cfg = settings.model_copy(update={'ai_max_retries':0, 'ai_max_output_tokens':2048})
    if not cfg.gemini_api_key.get_secret_value():
        raise SystemExit('Configure a provider key locally before an explicitly authorized live run.')
    rows=[]
    for folder in sorted((Path(__file__).parent / 'dataset').glob('case_*'))[:args.count]:
        meta=json.loads((folder/'labels.json').read_text())
        reviewer=AIReviewer(cfg)
        start=time.perf_counter()
        row={'case_id':meta['case_id']}
        try:
            findings=reviewer.analyze('evaluation/'+meta['case_id'],meta['file'],
                (folder/'patch.diff').read_text(),(folder/'after.py').read_text())
            row.update(status='completed',finding_count=len(findings))
        except AIReviewError as exc:
            row.update(status='failed',error=str(exc))
        row.update(seconds=time.perf_counter()-start,usage=reviewer.usage)
        rows.append(row)
    good=[r for r in rows if r['status']=='completed']
    times=sorted(r['seconds'] for r in good)
    usage=[u for r in good for u in r['usage']]
    def average(key):
        values=[u[key] for u in usage if isinstance(u.get(key),int)]
        return statistics.mean(values) if len(values)==len(good) and values else None
    output={'recorded_at':datetime.now(timezone.utc).isoformat(),'model':cfg.ai_model,
        'kind':'real provider requests only; excludes webhook/queue/static/publication',
        'attempted':len(rows),'completed':len(good),'failure_rate':1-len(good)/len(rows),
        'successful_median_seconds':statistics.median(times) if times else None,
        'successful_p95_seconds':times[math.ceil(.95*len(times))-1] if times else None,
        'average_input_tokens':average('promptTokenCount'),
        'average_output_tokens':average('candidatesTokenCount'),
        'average_thinking_tokens':average('thoughtsTokenCount'),
        'average_cost_usd':None,'cost_note':'Requires dated verified pricing for this model and all billed token categories.',
        'samples':rows}
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k!='samples'},indent=2))

if __name__=='__main__':main()
