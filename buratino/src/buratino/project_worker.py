"""Fresh-process execution for authored project modules."""

import contextlib
import io
import traceback


def execute_project(connection, source: str, filename: str) -> None:
    """Execute exactly the source supplied by the parent and return exports."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = {"__file__": filename, "__name__": "_buratino_authored_project"}
    try:
        code = compile(source, filename, "exec")
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            from buratino.drawers import register_eb20_profile

            register_eb20_profile()
            exec(code, namespace)
        exports = {
            name: namespace[name]
            for name in ("variables", "calculated", "project", "drawer_configs")
            if name in namespace
        }
        connection.send({"ok": True, "exports": exports})
    except SyntaxError as exc:
        connection.send(
            {
                "ok": False,
                "code": "project_syntax_error",
                "message": f"{exc.msg} at line {exc.lineno}, column {exc.offset}.",
            }
        )
    except Exception as exc:
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        captured = (stdout.getvalue() + stderr.getvalue()).strip()
        if captured:
            details += f"\nProject output before failure:\n{captured[-2000:]}"
        connection.send(
            {"ok": False, "code": "project_import_error", "message": details}
        )
    finally:
        connection.close()
