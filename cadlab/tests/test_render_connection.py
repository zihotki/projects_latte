"""Checks for selecting the correct viewer bridge from an external shell."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(os.environ.get("CADLAB_SOMA_SOURCE", Path(__file__).resolve().parents[1] / "soma-fork-work"))
spec = importlib.util.spec_from_file_location("cadlab_render", source / "python/soma/render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class RenderConnectionTests(unittest.TestCase):
    def test_profile_overrides_inherited_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            (profile / "bridge.json").write_text(json.dumps({"app": "127.0.0.1:1234", "token": "selected"}))
            with patch.dict(os.environ, {"SOMA_USER_DATA": str(profile), "SOMA_APP": "127.0.0.1:5678", "SOMA_APP_TOKEN": "other"}):
                self.assertEqual(render._connection("/project"), ("127.0.0.1:1234", "selected"))

    def test_missing_or_invalid_profile_never_uses_inherited_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            with patch.dict(os.environ, {"SOMA_USER_DATA": str(profile), "SOMA_APP": "127.0.0.1:5678", "SOMA_APP_TOKEN": "other"}):
                for contents in (None, "invalid", "{}", "null", "[]", '"text"',
                                 '{"app": [], "token": "x"}', '{"app": "127.0.0.1:1234", "token": 1}',
                                 '{"app": "127.0.0.1:1234", "token": " "}',
                                 '{"app": "example.com:1234", "token": "x"}',
                                 '{"app": "127.0.0.1:0", "token": "x"}',
                                 '{"app": "127.0.0.1:65536", "token": "x"}'):
                    if contents is not None:
                        (profile / "bridge.json").write_text(contents)
                    with self.assertRaisesRegex(render.RenderError, "unavailable"):
                        render._connection("/project")

    def test_native_environment_still_works_without_profile(self):
        with patch.dict(os.environ, {"SOMA_APP": "127.0.0.1:5678", "SOMA_APP_TOKEN": "native"}, clear=True):
            self.assertEqual(render._connection("/project"), ("127.0.0.1:5678", "native"))


if __name__ == "__main__":
    unittest.main()
