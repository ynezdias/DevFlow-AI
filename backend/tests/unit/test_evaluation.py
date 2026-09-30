# Evaluation harness is tested separately from provider calls.
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def evaluation():
    path = Path("/evaluation/evaluate.py")
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "evaluation" / "evaluate.py"
    if not path.exists():
        pytest.skip("Evaluation source mounted only for evaluation harness checks")
    spec = importlib.util.spec_from_file_location("evaluation_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_one_to_one_scoring(evaluation):
    expected=[dict(file="x.py",line=2,category="security")]
    item=dict(file_path="x.py",line_number=2,category="security")
    result=evaluation.score(expected,[item,item])
    assert (result["tp"],result["fp"],result["fn"])==(1,1,0)
    assert evaluation.score(expected,[])["fn"]==1
    assert evaluation.score([],[])["precision"] is None
