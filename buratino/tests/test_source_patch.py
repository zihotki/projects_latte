import json

from buratino.environment import source_status
from buratino.project import _identity_files


def test_source_status_accepts_engine_edits_and_checks_provenance(root, tmp_path):
    lock = json.loads((root / "cabineteer.lock.json").read_text())
    (tmp_path / "cabineteer.lock.json").write_text(json.dumps(lock))
    source = tmp_path / lock["source"] / "src/cabineteer"
    source.mkdir(parents=True)
    (source.parent.parent / "pyproject.toml").write_text("[project]\n")
    engine = source / "__init__.py"
    engine.write_text("original\n")
    assert source_status(tmp_path)["ok"]
    before = _identity_files(tmp_path)
    engine.write_text("changed\n")
    assert source_status(tmp_path)["ok"]
    assert _identity_files(tmp_path) != before
    lock["commit"] = "invalid"
    (tmp_path / "cabineteer.lock.json").write_text(json.dumps(lock))
    assert not source_status(tmp_path)["ok"]
