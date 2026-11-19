import pytest
from proofline.workspace_benchmark import benchmark_workspace_sync


def test_benchmark_detects_exactly_the_changed_documents():
    report = benchmark_workspace_sync(40, changed_fraction=0.1)

    assert report["documents"] == 40
    assert report["created"] == 40
    assert report["changed_documents"] == 4
    assert report["findings"] == 4
    assert all(report[key] >= 0 for key in report if key.endswith("_seconds"))


@pytest.mark.parametrize("documents,fraction", [(0, 0.1), (True, 0.1), (5, 0), (5, 1.5)])
def test_benchmark_rejects_invalid_parameters(documents, fraction):
    with pytest.raises(ValueError):
        benchmark_workspace_sync(documents, changed_fraction=fraction)
