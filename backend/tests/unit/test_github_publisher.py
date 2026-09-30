from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from app.services.github_publisher import GitHubPublisher, NAME
from app.services.github_service import GitHubError, TemporaryGitHubError


def fixture(count=1):
    review = SimpleNamespace(id=uuid4(), repository_name="owner/repo", pull_request_number=7,
        head_sha="a"*40, github_check_run_id=None, status="completed", publication_status=None,
        changed_files=[{"filename":"a.py","patch":f"@@ -0,0 +1,{max(count,1)} @@\n"+"\n".join("+x=1" for _ in range(max(count,1)))}],
        scope_summary={"limited":False})
    findings=[dict(file_path="a.py",line_number=i+1,source="ai",category="test",severity="high",
        title="Potential bug", description="Review this change",suggestion="Validate inputs") for i in range(count)]
    report={"review_id":str(review.id),"status":"completed","findings":findings,
        "analysis":{"static_analysis":"completed","ai_analysis":"completed"}}
    github=Mock()
    github.get_pull_request.return_value={"head":{"sha":review.head_sha}}
    github.list_check_runs.return_value=[]
    github.create_check_run.return_value={"id":42}
    github.list_check_annotations.return_value=[]
    return review,report,github,GitHubPublisher(github)


def test_create_reuses_id():
    review,report,github,publisher=fixture()
    assert publisher.create_check_run(review)==42
    assert publisher.create_check_run(review)==42
    github.create_check_run.assert_called_once()
    assert github.create_check_run.call_args.kwargs["status"]=="in_progress"
    assert github.create_check_run.call_args.kwargs["external_id"]==str(review.id)


def test_recover_remote_create_after_lost_response():
    review,report,github,publisher=fixture()
    github.list_check_runs.return_value=[dict(id=99,name=NAME,external_id=str(review.id),head_sha=review.head_sha)]
    assert publisher.create_check_run(review)==99
    github.create_check_run.assert_not_called()


def test_batches_and_retry_do_not_append_duplicates():
    review,report,github,publisher=fixture(101)
    publisher.create_check_run(review)
    remote=[]
    def update(repo,check_id,**kwargs):
        remote.extend(kwargs.get("output",{}).get("annotations",[]))
    github.update_check_run.side_effect=update
    github.list_check_annotations.side_effect=lambda *_:list(remote)
    publisher.update_check_run(review,report)
    batches=[call.kwargs["output"]["annotations"] for call in github.update_check_run.call_args_list if "annotations" in call.kwargs["output"]]
    assert [len(batch) for batch in batches]==[50,50,1]
    publisher.update_check_run(review,report)
    assert len(remote)==101
    assert github.update_check_run.call_args.kwargs["conclusion"]=="neutral"
    assert "Total findings: 101" in github.update_check_run.call_args.kwargs["output"]["summary"]


def test_lost_annotation_response_reconciled():
    review,report,github,publisher=fixture()
    publisher.create_check_run(review)
    remote=[]
    def update(repo,check_id,**kwargs):
        annotations=kwargs.get("output",{}).get("annotations",[])
        remote.extend(annotations)
        if annotations: raise TemporaryGitHubError("github_unavailable")
    github.update_check_run.side_effect=update
    github.list_check_annotations.side_effect=lambda *_:list(remote)
    with pytest.raises(TemporaryGitHubError): publisher.update_check_run(review,report)
    publisher.update_check_run(review,report)
    assert len(remote)==1


@pytest.mark.parametrize("existing", [False,True])
def test_stale_head(existing):
    review,report,github,publisher=fixture()
    review.github_check_run_id=42 if existing else None
    github.get_pull_request.return_value={"head":{"sha":"b"*40}}
    publisher.create_check_run(review)
    assert review.status=="superseded"
    github.create_check_run.assert_not_called()
    if existing:
        assert github.update_check_run.call_args.kwargs["conclusion"]=="cancelled"
        assert "annotations" not in github.update_check_run.call_args.kwargs["output"]


def test_head_changes_between_batches():
    review,report,github,publisher=fixture(51)
    publisher.create_check_run(review)
    github.get_pull_request.side_effect=[{"head":{"sha":review.head_sha}},{"head":{"sha":review.head_sha}},{"head":{"sha":"b"*40}}]
    publisher.update_check_run(review,report)
    assert review.status=="superseded"
    assert len(github.update_check_run.call_args_list)==2
    assert github.update_check_run.call_args.kwargs["conclusion"]=="cancelled"


@pytest.mark.parametrize("status,ai,expected",[("completed","completed","success"),("failed","failed","action_required"),("completed","disabled","neutral")])
def test_conclusion_policy(status,ai,expected):
    review,report,github,publisher=fixture(0)
    report["status"]=status
    report["analysis"]["ai_analysis"]=ai
    publisher.create_check_run(review)
    publisher.update_check_run(review,report)
    assert github.update_check_run.call_args.kwargs["conclusion"]==expected


def test_invalid_location_never_published():
    review,report,github,publisher=fixture()
    publisher.create_check_run(review)
    report["findings"][0]["line_number"]=500
    with pytest.raises(GitHubError,match="invalid_annotation_location"):
        publisher.update_check_run(review,report)
    github.update_check_run.assert_not_called()
