import type {Review} from '../types/review'
import {StatusBadge} from './StatusBadge'
export function ReviewCard({review}: {review: Review}) {
  const duration = review.completed_at && review.started_at ? Math.max(0, (Date.parse(review.completed_at)-Date.parse(review.started_at))/1000).toFixed(1) : null
  return <a className="review-card" href={`#/reviews/${review.id}`}>
    <div><h3>{review.repository_name} <span>? PR #{review.pull_request_number}</span></h3><p>{review.head_sha.slice(0, 8)} ? {new Date(review.created_at).toLocaleString()}</p></div>
    <div className="card-right"><StatusBadge status={review.status}/><p>{review.finding_count == null ? 'Report pending' : `${review.finding_count} findings`}{duration && ` ? ${duration}s`}</p></div>
  </a>
}
