export function StatusBadge({status}: {status: string}) {
  return <span className={`badge ${['completed','failed','processing','queued','superseded'].includes(status) ? status : ''}`}>{status.replaceAll('_', ' ')}</span>
}
