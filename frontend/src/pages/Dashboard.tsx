import {useCallback, useState} from 'react'
import {api} from '../services/api'
import {usePolling} from '../services/usePolling'
import {ReviewCard} from '../components/ReviewCard'
export function Dashboard() {
  const [page, setPage] = useState(1)
  const load = useCallback(async (signal: AbortSignal) => {const [reviews, metrics] = await Promise.all([api.reviews(page, signal), api.metrics(signal)]); return {reviews, metrics}}, [page])
  const {data, error} = usePolling(load)
  return <><div className="page-heading"><div><p className="eyebrow">REVIEW HISTORY</p><h1>Code Review Dashboard</h1><p>Static analysis and AI findings, in one place.</p></div><span className="live">Refreshes every 5 seconds</span></div>
    {error && <p role="alert" className="error">{error}</p>}
    {!data ? !error && <p role="status">Loading reviews?</p> : <>
    <section className="metrics" aria-label="Review counts">{[['Total reviews',data.metrics.total_reviews],['Completed',data.metrics.completed],['Processing',data.metrics.processing],['Failed',data.metrics.failed]].map(([label,value])=><article key={label}><p>{label}</p><strong>{value}</strong></article>)}</section>
    <div className="section-heading"><h2>Recent reviews</h2><span>{data.metrics.queued} queued ? {data.metrics.superseded} superseded</span></div>
    {data.reviews.items.length ? data.reviews.items.map(review=><ReviewCard key={review.id} review={review}/>) : <div className="empty"><h3>No reviews yet</h3><p>Open a pull request in a repository connected to your DevFlow GitHub App.</p></div>}
    <nav className="pagination" aria-label="Review pages"><button disabled={page===1} onClick={()=>setPage(page-1)}>Previous</button><span>Page {data.reviews.page} ? {data.reviews.total} reviews</span><button disabled={page*12>=data.reviews.total} onClick={()=>setPage(page+1)}>Next</button></nav>
    </>}
  </>
}
