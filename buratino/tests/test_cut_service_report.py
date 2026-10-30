"""Build downloads use the provider plans and remain revision-pinned."""

import csv
import json
import re
from io import BytesIO, StringIO
from threading import Event

import pytest

from buratino import preview
from buratino.build import _page
from buratino.cut_service_report import write_cutlists
from buratino.environment import file_hash, read_json


def part(ident, material="birch", thickness=18, *, quantity=1, panel_type="panel"):
    return {
        "id": ident,
        "material": material,
        "panel_type": panel_type,
        "quantity": quantity,
        "stock_mm": {"length": 400.2, "width": 180, "thickness": thickness},
        "grain_direction": "none",
        "grain_status": "nondirectional",
    }


def test_report_groups_mixed_materials_types_and_thicknesses(tmp_path):
    result = {
        "source_revision": "abc-revision",
        "input_identity": "identity",
        "parts": [
            part("a", quantity=501),
            part("b", thickness=16),
            part("c", material="oak"),
            part("d", panel_type="plywood"),
        ],
    }
    report = write_cutlists(tmp_path, result)
    assert 'id="cutlists"' in report
    assert "504 of 504 panels included" in report
    assert "rounded up" in report
    assert "banding machine trims before banding" in report
    assert 'href="report.html#part-drawings"' in report
    assert "default export configuration" in report
    assert "OPMAATZAGEN band syntax" not in report
    for provider, delimiter, header, files in (
        ("zagenzagen", ";", "Naam", 5),
        ("opmaatzagen", ",", "Aantal", 4),
    ):
        directory = tmp_path / "cutlists" / provider
        summary = read_json(directory / "index.json")
        assert summary["reports"]["review"] == "../../report.html"
        assert summary["reports"]["assembly"] == "../../report.html#assembly"
        assert summary["source_revision"] == result["source_revision"]
        assert summary["source_input_identity"] == "identity"
        assert len(summary["groups"]) == files
        assert sum(group["quantity"] for group in summary["groups"]) == 504
        assert {group["thickness_mm"] for group in summary["groups"]} == {16, 18}
        assert {group["panel_type"] for group in summary["groups"]} == {
            "panel",
            "plywood",
        }
        for group in summary["groups"]:
            path = directory / group["file"]
            rows = list(csv.reader(StringIO(path.read_text()), delimiter=delimiter))
            assert rows[0][0] == header
            assert f"cutlists/{provider}/{group['file']}" in report
            assert (
                sum(int(row[1 if delimiter == ";" else 0]) for row in rows[1:])
                == (group["quantity"])
            )
    assert "DRAFT — NOT FOR MANUFACTURING" not in _page("Test", report)


def test_report_keeps_partial_and_empty_export_issues_visible(tmp_path):
    bad = part("bad", quantity=3)
    bad["stock_mm"]["length"] = -1
    report = write_cutlists(tmp_path, {"parts": [part("good", quantity=2), bad]})
    assert "2 of 5 panels included" in report
    assert "1 source record omitted" in report
    assert 'id="zagenzagen-issues" open' in report
    assert "invalid_part" in report and "bad" in report
    summary = read_json(tmp_path / "cutlists/zagenzagen/index.json")
    assert summary["status"] == "partial"
    assert {item["source_id"]: item["outcome"] for item in summary["trace"]} == {
        "good": "exported",
        "bad": "omitted",
    }
    report = write_cutlists(tmp_path / "empty", {"parts": [bad]})
    assert "No CSV files available" in report
    assert "invalid_part" in report


@pytest.mark.parametrize("catalog", [False, True])
def test_preview_only_serves_manifest_listed_cutlists(tmp_path, monkeypatch, catalog):
    project = tmp_path / "projects/test"
    revision = "a" * 12 + "-" + "b" * 8
    directory = project / "build" / revision
    directory.mkdir(parents=True)
    report = write_cutlists(directory, {"parts": [part("a")]})
    (directory / "report.html").write_text(_page("Test", report))
    files = {
        path.relative_to(directory).as_posix(): file_hash(path)
        for path in directory.rglob("*")
        if path.is_file()
    }
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "status": "draft",
                "files": files,
            }
        )
    )
    (project / "build/latest.json").write_text(json.dumps({"revision": revision}))
    (directory / "cutlists/zagenzagen/unlisted.csv").write_text("private")

    class Watcher:
        def __init__(self, *_args):
            self.stop = Event()

        def close(self):
            pass

    class Server:
        def __init__(self, _address, handler):
            self.handler = handler

        def server_close(self):
            pass

    monkeypatch.setattr(preview, "ProjectWatcher", Watcher)
    monkeypatch.setattr(preview, "ThreadingHTTPServer", Server)
    monkeypatch.setattr(
        preview, "catalog_projects", lambda _root: [{"name": "test", "path": project}]
    )
    server = preview.preview_server(project, catalog_root=tmp_path if catalog else None)
    handler_type = server.handler.func
    prefix = "/designs/test/" if catalog else "/"

    def request(relative):
        handler = handler_type.__new__(handler_type)
        handler.path = prefix + relative
        handler.command = "GET"
        handler.wfile = BytesIO()
        responses = []
        handler.send_response = responses.append
        handler.send_error = responses.append
        handler.send_header = lambda *_args: None
        handler.end_headers = lambda: None
        stream = handler.send_head()
        payload = stream.read() if stream else handler.wfile.getvalue()
        if stream:
            stream.close()
        return responses, payload

    try:
        for route in ("", f"revisions/{revision}/"):
            responses, payload = request(route + "report.html")
            assert responses == [200]
            if not route:
                assert f"{prefix}revisions/{revision}/".encode() in payload
            for href in re.findall(r'href="(cutlists/[^"#]+)"', report):
                responses, payload = request(route + href)
                assert responses == [200]
                assert payload == (directory / href).read_bytes()
            for denied in (
                "cutlists/zagenzagen/unlisted.csv",
                "cutlists/zagenzagen/../index.json",
                "cutlists/zagenzagen/%2e%2e/index.json",
                "inputs/project.py",
            ):
                assert request(route + denied)[0] == [404]
    finally:
        server.server_close()
