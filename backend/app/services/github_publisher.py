"""Publish stored validated reports using installation authentication only.

Call under a review-row lock. Reconcile remote state before retrying writes because
GitHub appends annotations and does not provide an idempotency key for creation.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json

from app.services.diff_parser import parse_diff
from app.services.finding_validator import ValidatedFinding
from app.services.github_service import GitHubError

NAME = "DevFlow AI Code Review"


class GitHubPublisher:
    def __init__(self, github):
        self.github = github

    def current(self, review):
        pr = self.github.get_pull_request(review.repository_name, review.pull_request_number)
        return pr["head"]["sha"] == review.head_sha

    def supersede(self, review):
        review.status = "superseded"
        review.publication_status = "superseded"
        if review.github_check_run_id:
            self.github.update_check_run(review.repository_name, review.github_check_run_id,
                status="completed", conclusion="cancelled", output={"title": NAME,
                "summary": "Superseded: the pull request head changed. Findings were not published as the current review."})

    def create_check_run(self, review):
        if not self.current(review):
            self.supersede(review)
            return None
        if review.github_check_run_id:
            return review.github_check_run_id
        # Recover a create accepted by GitHub before the local ID could be committed.
        matches = [run for run in self.github.list_check_runs(review.repository_name, review.head_sha)
            if run.get("external_id") == str(review.id) and run.get("name") == NAME
            and run.get("head_sha") == review.head_sha]
        if matches:
            review.github_check_run_id = min(run["id"] for run in matches)
        else:
            result = self.github.create_check_run(review.repository_name, name=NAME,
                head_sha=review.head_sha, external_id=str(review.id), status="in_progress",
                started_at=datetime.now(timezone.utc).isoformat())
            review.github_check_run_id = result["id"]
        review.publication_status = "in_progress"
        return review.github_check_run_id

    def update_check_run(self, review, report):
        if not self.current(review):
            self.supersede(review)
            return
        if not review.github_check_run_id:
            raise GitHubError("github_check_id_missing")
        if report.get("review_id") != str(review.id) or report.get("status") not in {"completed", "failed"}:
            raise GitHubError("invalid_publication_report")
        changed = {file["filename"]: parse_diff(file["patch"]).added_lines
                   for file in review.changed_files or [] if file.get("patch")}
        annotations = []
        for raw in report["findings"]:
            data = {key: value for key, value in raw.items() if key in ValidatedFinding.model_fields}
            finding = ValidatedFinding.model_validate(data)
            if finding.line_number not in changed.get(finding.file_path, set()):
                raise GitHubError("invalid_annotation_location")
            message = finding.description
            if finding.suggestion:
                message += "\nSuggestion: " + finding.suggestion
            annotation = {"path": finding.file_path, "start_line": finding.line_number,
                "end_line": finding.line_number,
                "annotation_level": "notice" if finding.severity == "low" else "warning",
                "title": finding.title, "message": message[:8000]}
            marker = sha256(json.dumps(annotation, sort_keys=True).encode()).hexdigest()
            annotation["raw_details"] = "devflow-finding:" + marker
            annotations.append(annotation)
        counts = {level: sum(f["severity"] == level for f in report["findings"])
                  for level in ("high", "medium", "low")}
        states = report["analysis"]
        incomplete = report["status"] == "failed" or any(v == "failed" for v in states.values())
        limited = bool((review.scope_summary or {}).get("limited")) or any(v in {"limited", "disabled"} for v in states.values())
        # Findings are advisory, including AI high severity. Execution failure is separate.
        conclusion = "action_required" if incomplete else "neutral" if annotations or limited else "success"
        summary = (f"Status: {'Incomplete' if incomplete else 'Completed'}\n\n"
            f"Files analyzed (static): {len(review.changed_files or []) if states['static_analysis'] == 'completed' else 0}\n"
            f"Total findings: {len(annotations)}\nHigh severity: {counts['high']}\n"
            f"Medium severity: {counts['medium']}\nLow severity: {counts['low']}\n\n"
            f"Static analysis: {states['static_analysis']}\nAI analysis: {states['ai_analysis']}\n"
            f"Scope limited: {bool((review.scope_summary or {}).get('limited'))}\n\n"
            "Findings are advisory. Incomplete analysis requires attention; severity alone does not fail this check.")
        output = {"title": NAME, "summary": summary}
        existing = self.github.list_check_annotations(review.repository_name, review.github_check_run_id)
        seen = {item.get("raw_details") for item in existing}
        pending = [item for item in annotations if item["raw_details"] not in seen]
        for offset in range(0, len(pending), 50):
            if not self.current(review):
                self.supersede(review)
                return
            self.github.update_check_run(review.repository_name, review.github_check_run_id,
                output={**output, "annotations": pending[offset:offset+50]})
        if not self.current(review):
            self.supersede(review)
            return
        self.github.update_check_run(review.repository_name, review.github_check_run_id,
            status="completed", conclusion=conclusion, output=output)
        review.publication_status = "published"
