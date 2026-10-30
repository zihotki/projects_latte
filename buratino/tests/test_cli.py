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


def test_short_project_names_resolve_to_project_folders(root):
    assert (
        cli.project_path(root, "two-under-window") == root / "projects/two-under-window"
    )
    assert (
        cli.project_path(root, "projects/two-under-window")
        == root / "projects/two-under-window"
    )


def test_short_project_names_cannot_escape_projects(root):
    from buratino.project import InputError

    try:
        cli.project_path(root, "../outside")
    except InputError as exc:
        assert exc.code == "invalid_project_path"
    else:
        raise AssertionError("Expected path validation to reject traversal")


def test_explicit_preview_refreshes_then_starts_server(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "root_dir", lambda: root)
    calls = []
    monkeypatch.setattr(
        cli, "ensure_current_build", lambda base, path: calls.append(path)
    )

    class Server:
        server_port = 1234

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "preview_server", lambda path, port: Server())
    assert cli.main(["preview", "two-under-window"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["url"] == "http://127.0.0.1:1234/preview.html"
    assert calls == [root / "projects/two-under-window"]


def test_default_preview_refreshes_only_tagged_designs(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "root_dir", lambda: root)
    calls = []
    monkeypatch.setattr(
        cli, "ensure_current_build", lambda base, path: calls.append(path)
    )

    class Server:
        server_port = 4321

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "preview_catalog_server", lambda base, port: Server())
    assert cli.main(["preview"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["url"] == "http://127.0.0.1:4321/"
    assert calls == [
        root / "projects/real-assembly-native",
        root / "projects/two-under-window",
    ]
