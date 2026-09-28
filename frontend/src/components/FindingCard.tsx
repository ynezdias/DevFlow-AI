import type {Finding} from '../types/review'
export function FindingCard({finding}: {finding: Finding}) {
  return <article className="finding"><div className="finding-meta"><span className={`badge ${finding.severity}`}>{finding.severity}</span><span>{(finding.sources || [finding.source]).join(' + ')} ? {finding.category}</span></div>
    <h3>{finding.title}</h3><code>{finding.file_path}:{finding.line_number}</code><p className="plain-text">{finding.description}</p>
    {finding.suggestion && <div className="suggestion"><strong>Suggested fix</strong><p className="plain-text">{finding.suggestion}</p></div>}
  </article>
}
