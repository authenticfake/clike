"""A promoted REQ's regression installs the candidate's npm dependencies when they are a superset."""
import json
from pathlib import Path

from eval_runner import EvalRunner


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def _setup(tmp_path: Path, promoted: dict, candidate: dict):
    project = tmp_path / "project"
    candidate_kit = project / "runs/kit/REQ-024"
    _write(candidate_kit / "ci/package.json", candidate)
    _write(candidate_kit / "ci/package-lock.json", '{"lockfileVersion": 3, "name": "candidate"}')
    (candidate_kit / "src").mkdir(parents=True)
    work = tmp_path / "work/REQ-002"
    _write(work / "ci/package.json", promoted)
    _write(work / "ci/package-lock.json", '{"lockfileVersion": 3, "name": "promoted"}')
    runner = EvalRunner(project, eval_key="REQ-024/regression/REQ-002", extra_src_roots=[candidate_kit / "src"], regression=True)
    return runner, work


V1 = {"dependencies": {"next": "16.4.6", "react": "19.3.1"}, "devDependencies": {"@playwright/test": "1.65.0"}}
V2 = {"dependencies": {"next": "16.4.6", "react": "19.3.1", "tailwindcss": "4.2.0", "lucide-react": "0.600.0"},
      "devDependencies": {"@playwright/test": "1.65.0"}}


def test_a_superset_candidate_manifest_and_its_lock_are_adopted(tmp_path: Path):
    runner, work = _setup(tmp_path, V1, V2)
    assert runner._adopt_candidate_node_manifests(work) == ["ci/package.json"]
    assert json.loads((work / "ci/package.json").read_text())["dependencies"]["tailwindcss"] == "4.2.0"
    assert '"candidate"' in (work / "ci/package-lock.json").read_text()


def test_a_version_conflict_or_a_missing_dependency_keeps_the_promoted_manifest(tmp_path: Path):
    for n, candidate in enumerate(({**V2, "dependencies": {**V2["dependencies"], "react": "19.4.0"}},   # another version
                                   {"dependencies": {"next": "16.4.6", "tailwindcss": "4.2.0"}})):    # react dropped
        runner, work = _setup(tmp_path / str(n), V1, candidate)
        assert runner._adopt_candidate_node_manifests(work) == []
        assert "tailwindcss" not in (work / "ci/package.json").read_text()
        assert '"promoted"' in (work / "ci/package-lock.json").read_text()


def test_outside_a_regression_nothing_changes(tmp_path: Path):
    runner, work = _setup(tmp_path, V1, V2)
    runner.regression = False
    assert runner._adopt_candidate_node_manifests(work) == []
    assert "tailwindcss" not in (work / "ci/package.json").read_text()
