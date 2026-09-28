import {useCallback} from 'react'
import {api} from '../services/api'
import {usePolling} from '../services/usePolling'
import {FindingCard} from '../components/FindingCard'
import {StatusBadge} from '../components/StatusBadge'
export function ReviewDetails({id}: {id: string}) {
 const load = useCallback(async (signal: AbortSignal) => {const [review,raw] = await Promise.all([api.review(id,signal),api.findings(id,signal)]); return {review,raw}},[id])
 const {data,error} = usePolling(load)
 const review=data?.review, report=review?.scope_summary?.report
 return <><a className="back" href="#/">? Review history</a>{error && <p role="alert" className="error">{error}</p>}
 {!review ? !error && <p role="status">Loading review?</p> : <>
 <div className="page-heading"><div><p className="eyebrow">PULL REQUEST #{review.pull_request_number}</p><h1>{review.repository_name}</h1><code>{review.head_sha}</code></div><StatusBadge status={review.status}/></div>
 <section className="detail-summary"><p>Created {new Date(review.created_at).toLocaleString()}</p><p>GitHub publication: <strong>{review.publication_status || 'Not published'}</strong></p>
 {review.github_check_run_id && <a href={`https://github.com/${review.repository_name.split('/').map(encodeURIComponent).join('/')}/runs/${review.github_check_run_id}`} target="_blank" rel="noreferrer">View GitHub Check ?</a>}
 {report && <p>Static analysis: <strong>{report.analysis.static_analysis}</strong> ? AI analysis: <strong>{report.analysis.ai_analysis}</strong></p>}
 {review.error_code && <p className="error">Review incomplete: {review.error_code}. Available findings are preserved.</p>}
 {review.scope_summary?.limited && <p>Scope was limited. Some files or analysis steps were skipped.</p>}
 </section><h2>{report ? `${report.summary.total_findings} validated findings` : 'Findings'}</h2>
 {!report && <p>No validated report is available yet. {data?.raw.length || 0} raw findings stored; awaiting a validated report.</p>}
 {report && report.findings.length===0 && <div className="empty">{report.status==='completed' ? 'No findings in the analyzed scope.' : 'No findings available. Analysis was incomplete.'}</div>}
 {report?.findings.map((finding,index)=><FindingCard key={`${finding.file_path}:${finding.line_number}:${finding.category}:${index}`} finding={finding}/>)}
 </>}
 </>
}
