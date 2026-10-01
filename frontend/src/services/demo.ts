import type {Review, Finding, Metrics} from '../types/review'

// Public, synthetic fixture only. No repository data or credentials are bundled.
const findings: Finding[] = [{file_path:'fixture.py',line_number:4,source:'bandit',
 severity:'high',category:'B605',title:'Shell execution (sample)',
 description:'This illustrative finding shows how a review appears. Passing an untrusted command to a shell can execute unintended commands.',
 suggestion:'Use a fixed executable and an argument list with shell=False.'}]
const review: Review = {id:'00000000-0000-4000-8000-000000000001',
 repository_name:'sample/python-review',pull_request_number:1,head_sha:'a'.repeat(40),
 status:'completed',created_at:'2026-09-30T12:00:00Z',started_at:null,completed_at:null,
 error_code:null,publication_status:'not_published',github_check_run_id:null,finding_count:1,
 scope_summary:{limited:false,report:{status:'completed',
 summary:{total_findings:1,high:1,medium:0,low:0},findings,
 analysis:{static_analysis:'sample',ai_analysis:'not_run'}}}}
const metrics: Metrics = {total_reviews:1,completed:1,processing:0,queued:0,failed:0,superseded:0}

export function demoResponse(path: string): unknown {
 if(path==='/metrics/summary') return metrics
 if(path.startsWith('/reviews?')) return {items:[review],total:1,page:1,page_size:12}
 if(path===`/reviews/${review.id}`) return review
 if(path===`/reviews/${review.id}/findings`) return findings
 throw new Error('Review not found in this sample demo.')
}
