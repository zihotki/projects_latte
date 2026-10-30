"""Capture provider plans beside a build and render their download table."""

import csv
import html
import io
import json
from pathlib import Path

from .cut_services import plan_export


def write_cutlists(
    directory: Path, result: dict, part_codes: dict[str, str] | None = None
) -> str:
    """Use the captured result and default config for both provider plans."""
    part_codes = part_codes or {}
    sections = []
    for provider in ("zagenzagen", "opmaatzagen"):
        plan = plan_export(result, provider)
        output = directory / "cutlists" / provider
        output.mkdir(parents=True, exist_ok=True)
        for name, content in plan.files.items():
            (output / name).write_text(content, encoding="utf-8")
        index = {
            "schema_version": 1,
            **plan.summary,
            "source_input_identity": result.get("input_identity"),
            "configuration": "default",
            "reports": {
                "review": "../../report.html",
                "assembly": "../../report.html#assembly",
            },
            "files": list(plan.files),
        }
        (output / "index.json").write_text(
            json.dumps(index, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        prefix = f"cutlists/{provider}/"
        issues = plan.summary["issues"]
        included = sum(group["quantity"] for group in plan.summary["groups"])
        quantities = [
            part.get("quantity", 1) if isinstance(part, dict) else None
            for part in result["parts"]
        ]
        total = (
            sum(quantities)
            if all(type(value) is int and value > 0 for value in quantities)
            else None
        )
        coverage = (
            f"{included} of {total} panels included. "
            if total is not None
            else f"{included} panels included. "
        )
        omitted = sum(item["outcome"] == "omitted" for item in plan.summary["trace"])
        issue_id = f"{provider}-issues"
        rows = []
        for group in plan.summary["groups"]:
            relevant = any(
                issue.get("part_id") in (None, *group["source_ids"]) for issue in issues
            )
            status = (
                f'<a href="report.html#{issue_id}">Review issues</a>'
                if relevant
                else "Included"
            )
            count = (
                len(
                    list(
                        csv.reader(
                            io.StringIO(plan.files[group["file"]]),
                            delimiter=";" if provider == "zagenzagen" else ",",
                        )
                    )
                )
                - 1
            )
            href = prefix + html.escape(group["file"], quote=True)
            rows.append(
                "<tr>"
                f"<td>{html.escape(group['material'])}</td>"
                f"<td>{html.escape(group['panel_type'])}</td>"
                f"<td>{group['thickness_mm']:g}</td>"
                f"<td>{group['quantity']}</td><td>{count}</td><td>{status}</td>"
                f'<td><a download href="{href}">'
                "Download CSV</a></td></tr>"
            )
        issue_list = "".join(
            f"<li><code>{html.escape(issue['code'])}</code>"
            + (
                f" ({html.escape(part_codes.get(issue['part_id'], issue['part_id']))})"
                if issue.get("part_id") is not None
                else ""
            )
            + f": {html.escape(issue['message'])}</li>"
            for issue in issues
        )
        sections.append(
            f"<h3>{provider.upper()}</h3><p>{coverage}"
            + (
                f"{omitted} source record{'s' if omitted != 1 else ''} omitted. "
                if omitted
                else ""
            )
            + f'<a href="{prefix}index.json">Export details and source trace</a>.</p>'
            + (
                "<table><thead><tr><th>Material</th><th>Type</th><th>Thickness, mm</th>"
                "<th>Panels</th><th>Rows</th><th>Status</th><th>Download</th></tr>"
                "</thead><tbody>" + "".join(rows) + "</tbody></table>"
                if rows
                else "<p>No CSV files available.</p>"
            )
            + (
                f'<details id="{issue_id}"'
                + (" open" if omitted else "")
                + f"><summary>{len(issues)} export issues</summary><ul>"
                + issue_list
                + "</ul></details>"
                if issues
                else ""
            )
            + (
                "<p>OPMAATZAGEN band syntax is best effort. Check side labels and "
                "the shared finish type in the provider import screen.</p>"
                if provider == "opmaatzagen"
                and any(
                    edge.get("kind") == "band"
                    for item in plan.summary["trace"]
                    for edge in item.get("edges", {}).values()
                )
                else ""
            )
        )
    return (
        '<section id="cutlists"><h2>Cut lists</h2>'
        "<p>Upload one CSV per material, panel type and thickness group. Large "
        "groups can have separate CSV files. These files contain rectangular stock "
        "blanks. Fractional dimensions are rounded up to whole millimetres. Length "
        "follows the authored grain direction when known.</p>"
        "<p>Select the material product on the cutting service website and check "
        "its import preview. The banding machine trims before banding; CSV sizes "
        "have no band thickness compensation. Unsupported machining is documented "
        'in the <a href="report.html#part-drawings">part drawings</a>.</p>'
        "<p>These downloads use the default export configuration. For custom "
        "material, grain or finish settings, use the export-cutlist CLI with "
        "--config.</p>" + "".join(sections) + "</section>"
    )
