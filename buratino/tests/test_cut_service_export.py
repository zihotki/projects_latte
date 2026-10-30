import json

import pytest

from buratino import cli, cut_service_export
from buratino.cut_services import plan_export
from buratino.environment import file_hash
from buratino.project import InputError


def _captured_project(tmp_path, monkeypatch, *, quantity=501):
    project = tmp_path / "project"
    project.mkdir()
    identity = "input-identity"
    revision = "a" * 12 + "-" + "b" * 8
    build = project / "build" / revision
    build.mkdir(parents=True)
    result = {
        "input_identity": identity,
        "parts": [
            {
                "id": "panel.one",
                "material": "birch",
                "quantity": quantity,
                "blank_mm": {"length": 600, "width": 300, "thickness": 18},
            }
        ],
    }
    (build / "result.json").write_text(json.dumps(result), encoding="utf-8")
    monkeypatch.setattr(
        cut_service_export,
        "latest_build",
        lambda _project: (build, {"revision": revision, "input_identity": identity}),
    )
    monkeypatch.setattr(
        cut_service_export,
        "input_status",
        lambda *_args: {"status": "current"},
    )
    return project, build, identity, revision


def test_export_and_reexport_replace_old_chunks(tmp_path, monkeypatch):
    project, build, _, revision = _captured_project(tmp_path, monkeypatch)
    first = cut_service_export.export_cutlist(project, "zagenzagen")
    output = project / "exports" / revision / "zagenzagen"
    assert first["status"] in {"complete", "review"}
    assert len(first["files"]) == 3  # Two CSV chunks and the index.
    index = json.loads((output / "index.json").read_text(encoding="utf-8"))
    assert index["source_revision"] == revision
    assert index["provider_product_selection_required"] is True
    assert index["reports"]["review"].endswith("/report.html")
    assert index["file_context"]

    result_path = build / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["parts"][0]["quantity"] = 1
    result_path.write_text(json.dumps(result), encoding="utf-8")
    second = cut_service_export.export_cutlist(project, "zagenzagen")
    assert len(second["files"]) == 2
    assert not list(output.glob("*-002.csv"))
    assert len(list(output.glob("*.csv"))) == 1


def test_export_refuses_nonempty_unowned_directory(tmp_path, monkeypatch):
    project, _, _, _ = _captured_project(tmp_path, monkeypatch)
    output = tmp_path / "customer-files"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="unowned"):
        cut_service_export.export_cutlist(project, "opmaatzagen", output_path=output)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_export_refuses_symlink_output(tmp_path, monkeypatch):
    project, _, _, _ = _captured_project(tmp_path, monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    output = tmp_path / "linked-output"
    output.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        cut_service_export.export_cutlist(project, "zagenzagen", output_path=output)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_export_rejects_stale_build(tmp_path, monkeypatch):
    project, _, _, _ = _captured_project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cut_service_export,
        "input_status",
        lambda *_args: {"status": "stale"},
    )
    with pytest.raises(InputError, match="Run build first"):
        cut_service_export.export_cutlist(project, "zagenzagen")


def test_cli_returns_two_for_review_and_one_for_invalid_provider(
    root, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "root_dir", lambda: root)
    monkeypatch.setattr(
        cli,
        "export_cutlist",
        lambda *_args, **_kwargs: {
            "status": "review",
            "provider": "opmaatzagen",
            "physical_panels": 1,
            "files": ["one.csv", "index.json"],
            "group_count": 1,
            "issue_count": 1,
            "provider_product_selection_required": True,
            "directory": "/tmp/export",
        },
    )
    assert (
        cli.main(
            [
                "export-cutlist",
                "projects/simple-cabinet",
                "--provider",
                "opmaatzagen",
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "review"

    monkeypatch.setattr(cli, "export_cutlist", cut_service_export.export_cutlist)
    assert (
        cli.main(["export-cutlist", "projects/simple-cabinet", "--provider", "unknown"])
        == 1
    )
    assert "Unknown provider" in json.loads(capsys.readouterr().err)["message"]


def test_export_does_not_accept_a_build_result_with_wrong_identity(
    tmp_path, monkeypatch
):
    project, build, _, _ = _captured_project(tmp_path, monkeypatch)
    result_path = build / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["input_identity"] = "different"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(InputError, match="identity"):
        cut_service_export.export_cutlist(project, "zagenzagen")


def test_export_keeps_review_index_when_no_panel_row_is_safe(tmp_path, monkeypatch):
    project, build, _, revision = _captured_project(tmp_path, monkeypatch, quantity=1)
    result_path = build / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["parts"][0]["blank_mm"]["length"] = 0
    result_path.write_text(json.dumps(result), encoding="utf-8")

    exported = cut_service_export.export_cutlist(project, "zagenzagen")
    output = project / "exports" / revision / "zagenzagen"
    assert exported["status"] == "partial"
    assert exported["files"] == ["index.json"]
    index = json.loads((output / "index.json").read_text(encoding="utf-8"))
    assert index["issues"][0]["severity"] == "partial"
    assert index["trace"][0]["outcome"] == "omitted"


def test_export_rejects_tampered_captured_build(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    revision = "c" * 12 + "-" + "d" * 8
    build = project / "build" / revision
    build.mkdir(parents=True)
    result_path = build / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "input_identity": "identity",
                "parts": [
                    {
                        "id": "panel.one",
                        "material": "birch",
                        "blank_mm": {
                            "length": 600,
                            "width": 300,
                            "thickness": 18,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "build" / "latest.json").write_text(
        json.dumps({"revision": revision}), encoding="utf-8"
    )
    (build / "manifest.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "status": "draft",
                "input_identity": "identity",
                "files": {"result.json": file_hash(result_path)},
            }
        ),
        encoding="utf-8",
    )
    result_path.write_text(
        result_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )
    monkeypatch.setattr(
        cut_service_export,
        "input_status",
        lambda *_args: {"status": "current"},
    )
    with pytest.raises(InputError, match="Run build first"):
        cut_service_export.export_cutlist(project, "zagenzagen")


def test_core_summary_is_used_for_file_context():
    planned = plan_export(
        {
            "source_revision": "r1",
            "parts": [
                {
                    "id": "panel.one",
                    "material": "birch",
                    "blank_mm": {"length": 600, "width": 300, "thickness": 18},
                }
            ],
        },
        "zagenzagen",
    )
    assert planned.summary["provider_product_selection_required"] is True
    assert planned.summary["groups"][0]["thickness_mm"] == 18
