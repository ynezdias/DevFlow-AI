import type {Review, ReviewPage, Metrics, Finding} from '../types/review'
import {demoResponse} from './demo'
export const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (demoMode) return demoResponse(path) as T
  const response = await fetch(`/api${path}`, {signal})
  if (!response.ok) throw new Error(response.status === 404 ? 'Review not found.' : `API request failed (${response.status}). Check that the backend is running.`)
  return response.json() as Promise<T>
}
export const api = {
  reviews: (page: number, signal?: AbortSignal) => get<ReviewPage>(`/reviews?page=${page}&page_size=12`, signal),
  metrics: (signal?: AbortSignal) => get<Metrics>('/metrics/summary', signal),
  review: (id: string, signal?: AbortSignal) => get<Review>(`/reviews/${encodeURIComponent(id)}`, signal),
  findings: (id: string, signal?: AbortSignal) => get<Finding[]>(`/reviews/${encodeURIComponent(id)}/findings`, signal),
}
