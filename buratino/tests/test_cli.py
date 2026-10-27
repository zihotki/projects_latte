import json

from buratino import cli
from buratino.cli import main


def test_doctor_and_path_errors_have_machine_readable_status(root, monkeypatch, capsys):
    monkeypatch.setenv("BURATINO_ROOT", str(root))
    assert main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert main(["build", "../../outside"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_project_path"


def test_missing_project_has_failure_status(root, monkeypatch, capsys):
    monkeypatch.setenv("BURATINO_ROOT", str(root))
    assert main(["build", "projects/not-a-real-project"]) == 1
    assert json.loads(capsys.readouterr().err)["code"] == "input_unreadable"


def test_build_output_modes(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "root_dir", lambda: root)
    result = {
        "status": "draft",
        "manufacturing_ready": False,
        "directory": "/tmp/draft",
        "checks": [{"code": "example"}],
    }
    monkeypatch.setattr(cli, "build_project", lambda root, path: result)

    assert cli.main(["build", "projects/simple-cabinet"]) == 0
    output = capsys.readouterr().out
    assert "/tmp/draft" in output
    assert "report.html" in output
    assert "example" not in output

    assert cli.main(["build", "projects/simple-cabinet", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == result
