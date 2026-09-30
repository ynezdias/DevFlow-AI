import pytest
from pydantic import ValidationError
from app.config import Settings
from app.schemas.changed_file import ChangedFile
from app.services.review_scope import select_review_files


def file(name="app.py", patch="abcd", **kw):
    return ChangedFile(filename=name, patch=patch, status=kw.get("status", "modified"), additions=1, deletions=0, changes=1)


def limits(**kw):
    return Settings(_env_file=None, **kw)


@pytest.mark.parametrize("name,patch,reason", [
    ("photo.png", "text", "unsupported_extension"),
    ("vendor/app.py", "text", "ignored_directory"),
    ("src/generated/app.py", "text", "ignored_directory"),
    ("poetry.lock", "text", "lock_file"),
    ("message_pb2.py", "text", "generated_file"),
    ("app.py", "+# auto-generated", "generated_file"),
    ("app.py", None, "missing_patch"),
    ("app.py", "a\x00b", "binary_patch"),
])
def test_exclusions(name, patch, reason):
    selected, summary = select_review_files([file(name,patch)])
    assert selected == []
    assert summary.limited
    assert summary.skipped_files[0].reason == reason


def test_exact_limits_and_no_truncation():
    selected, summary = select_review_files([file("a.py"),file("b.py"),file("c.py")],limits(max_files=2,max_patch_chars_per_file=4,max_total_patch_chars=8))
    assert [f.filename for f in selected] == ["a.py","b.py"]
    assert [f.patch for f in selected] == ["abcd","abcd"]
    assert summary.total_patch_chars == 8
    assert summary.skipped_files[0].reason == "max_files"


def test_large_file_skipped_then_smaller_file_selected():
    selected, summary = select_review_files([file("a.py","12345"),file("b.py","1234"),file("c.py","12"),file("d.py","1")],limits(max_patch_chars_per_file=4,max_total_patch_chars=5))
    assert [f.filename for f in selected] == ["b.py","d.py"]
    assert [f.reason for f in summary.skipped_files] == ["max_patch_chars_per_file","max_total_patch_chars"]


def test_order_is_deterministic():
    files=[file("b.py"),file("a.py")]
    assert select_review_files(files,limits(max_files=1)) == select_review_files(list(reversed(files)),limits(max_files=1))


def test_empty_pr():
    selected, summary = select_review_files([])
    assert selected == [] and not summary.limited and summary.total_files == 0


def test_limits_are_validated():
    with pytest.raises(ValidationError):
        limits(max_files=0)
