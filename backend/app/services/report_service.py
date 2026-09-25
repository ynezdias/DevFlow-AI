"""Deterministic report assembly; originals are retained for inspection."""
from app.services.finding_validator import FindingValidator, ReviewedFile


class ReportService:
    def generate(self, review_id, findings, files, *, status, static_analysis, ai_analysis):
        originals = [f.model_dump() if hasattr(f, "model_dump") else f for f in findings]
        locations = {f.filename: ReviewedFile.from_source(f) for f in files}
        accepted, rejected = FindingValidator().validate(originals, locations)
        groups = {}
        rank = {"high": 0, "medium": 1, "low": 2}
        # Exact categories only: no speculative semantic merging of rule IDs.
        for index, finding in accepted:
            key = (finding.file_path, finding.line_number, finding.category)
            groups.setdefault(key, []).append((index, finding))
        merged = []
        for key in sorted(groups):
            entries = groups[key]
            representative = min(entries, key=lambda item: (
                rank[item[1].severity], item[1].source, item[1].title,
                item[1].description, item[1].suggestion or ""))[1]
            merged.append({**representative.model_dump(),
                "original_indices": [index for index, _ in entries],
                "sources": sorted({f.source for _, f in entries})})
        summary = {"total_findings": len(merged), **{
            level: sum(f["severity"] == level for f in merged) for level in rank}}
        return {"review_id": str(review_id), "status": status, "summary": summary,
                "findings": merged, "analysis": {"static_analysis": static_analysis,
                "ai_analysis": ai_analysis}, "original_findings": originals,
                "rejected_findings": rejected}
