import json

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
