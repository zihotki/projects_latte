from io import BytesIO

from buratino import preview
from buratino.project import InputError


def test_catalog_reads_metadata_and_lists_projects_without_loading_them(root):
    entries = preview.catalog_projects(root)
    by_name = {entry["name"]: entry for entry in entries}
    assert by_name["two-under-window"]["kind"] == "design"
    assert by_name["two-under-window"]["title"] == "Two under window"
    assert by_name["real-assembly-native"]["kind"] == "design"
    assert by_name["spaces-fixed-open"]["kind"] == "example"
    assert all(entry["path"].is_dir() for entry in entries)


def test_catalog_html_groups_designs_and_examples(root):
    page = preview._catalog_html(preview.catalog_projects(root)).decode()
    assert page.index("<h2>Designs</h2>") < page.index("<h2>Examples and tests</h2>")
    assert "Two under window" in page
    assert "Real assembly native" in page
    assert "spaces-fixed-open" in page


def test_catalog_root_request_returns_index(root, monkeypatch):
    monkeypatch.setattr(
        preview, "ThreadingHTTPServer", lambda _address, handler: handler
    )
    handler_type = preview.preview_catalog_server(root).func
    handler = handler_type.__new__(handler_type)
    responses = []
    handler.path = "/"
    handler.command = "GET"
    handler.wfile = BytesIO()
    handler.send_response = responses.append
    handler.send_error = responses.append
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None

    handler.send_head()

    assert responses == [200]
    assert b"<h2>Designs</h2>" in handler.wfile.getvalue()


def test_catalog_route_allows_only_known_project_names(root):
    projects = {
        entry["name"]: entry["path"] for entry in preview.catalog_projects(root)
    }
    allowed = preview._catalog_project_route(
        "designs/two-under-window/preview.html", projects
    )
    assert allowed == (
        root / "projects/two-under-window",
        "preview.html",
    )
    assert (
        preview._catalog_project_route("designs/unknown/preview.html", projects) is None
    )
    assert preview._catalog_project_route("designs/../preview.html", projects) is None


def test_ensure_current_build_rebuilds_when_latest_is_unavailable(
    root, tmp_path, monkeypatch
):
    calls = []
    project = tmp_path / "project"
    lookups = iter(
        [
            InputError("build_unavailable", "missing"),
            (tmp_path / "build", {"revision": "fresh"}),
        ]
    )

    def latest(_path):
        value = next(lookups)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(preview, "latest_build", latest)
    monkeypatch.setattr(
        preview, "build_project", lambda base, path: calls.append((base, path))
    )
    assert preview.ensure_current_build(root, project) == (
        tmp_path / "build",
        {"revision": "fresh"},
    )
    assert calls == [(root, project)]
