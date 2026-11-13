"""Checks for CAD Lab's shared runtime and project selection."""

import importlib.machinery
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / 'bin/cadlab'
loader = importlib.machinery.SourceFileLoader('cadlab_wrapper', str(script))
spec = importlib.util.spec_from_loader(loader.name, loader)
cadlab = importlib.util.module_from_spec(spec)
loader.exec_module(cadlab)


class WrapperTests(unittest.TestCase):
    def test_fine_mesh_export_and_explicit_override(self):
        self.assertEqual(cadlab.soma_arguments(['export', '--all', '--format', 'stl'])[-2:], ['--detail', 'fine'])
        self.assertEqual(cadlab.soma_arguments(['export', '--all', '--format=stl', '--detail=coarse'])[-1], '--detail=coarse')
        self.assertNotIn('--detail', cadlab.soma_arguments(['export', '--all', '--format', 'step']))

    def test_project_option_matches_native_last_and_abbreviated_argument(self):
        args = ['build', '--project', '/tmp/first', '--proj=/tmp/second']
        self.assertEqual(cadlab.project_arg(args), Path('/tmp/second').resolve())
        self.assertIsNone(cadlab.project_arg(['build', '--project']))

    def test_profiles_follow_canonical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a').mkdir()
            (root / 'b').mkdir()
            (root / 'alias').symlink_to(root / 'a', target_is_directory=True)
            self.assertEqual(cadlab.profile_for(root / 'a'), cadlab.profile_for(root / 'alias'))
            self.assertNotEqual(cadlab.profile_for(root / 'a'), cadlab.profile_for(root / 'b'))

    def test_symlinked_environment_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, other = root / 'project', root / 'other'
            (project / '.soma').mkdir(parents=True)
            other.mkdir()
            (other / 'keep').write_text('keep')
            (project / '.soma/env').symlink_to(other, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'local folder'):
                cadlab.prepare_environment(project)
            self.assertEqual((other / 'keep').read_text(), 'keep')

    def test_requirements_symlink_outside_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / 'project'
            project.mkdir()
            (root / 'requirements.txt').write_text('example\n')
            (project / 'requirements.txt').symlink_to(root / 'requirements.txt')
            with self.assertRaisesRegex(ValueError, 'inside the project'):
                cadlab.prepare_environment(project)

    def test_project_inside_installation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / 'SOMA'
            project = install / 'source' / 'project'
            project.mkdir(parents=True)
            with patch.object(cadlab, 'INSTALL', install):
                with self.assertRaisesRegex(ValueError, 'outside the shared SOMA'):
                    cadlab.reject_install_project(project)
                alternate = Path(tmp) / 'soma' / 'source' / 'project'
                if alternate.exists():
                    with self.assertRaisesRegex(ValueError, 'outside the shared SOMA'):
                        cadlab.reject_install_project(alternate)

    def test_source_update_lock_rejects_competing_installs(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.object(cadlab, 'HOME', home), (home / '.install.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, 'Another CAD Lab'):
                    cadlab.install()

    def test_existing_install_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            marker = home / 'marker'
            marker.write_text('{}')
            with patch.object(cadlab, 'HOME', home), patch.object(cadlab, 'MARKER', marker), \
                 patch.object(cadlab, 'installed', return_value={'branch': 'test', 'commit': 'abc'}), \
                 patch.object(cadlab, 'run') as run:
                cadlab.install()
                run.assert_not_called()

    def test_unrecognized_installation_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            installation = home / 'SOMA'
            installation.mkdir()
            (installation / 'user-file').write_text('keep')
            with patch.object(cadlab, 'HOME', home), patch.object(cadlab, 'INSTALL', installation), \
                 patch.object(cadlab, 'SOURCE', installation / 'source'), patch.object(cadlab, 'MARKER', installation / 'installation.json'):
                with self.assertRaisesRegex(ValueError, 'not a recognized'):
                    cadlab.install(update=True)
            self.assertEqual((installation / 'user-file').read_text(), 'keep')

    def test_repair_fetches_installed_commit_not_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            installation = home / 'SOMA'
            installation.mkdir()
            marker = installation / 'installation.json'
            marker.write_text(json.dumps({'branch': 'other', 'commit': 'selected-commit', 'repository': 'test-repo'}))
            calls = []

            def fake_run(*args, **kwargs):
                calls.append(args)
                if args[:2] == ('git', 'fetch'):
                    raise subprocess.CalledProcessError(1, args)
                return ''

            with patch.object(cadlab, 'HOME', home), patch.object(cadlab, 'INSTALL', installation), \
                 patch.object(cadlab, 'SOURCE', installation / 'source'), patch.object(cadlab, 'MARKER', marker), \
                 patch.object(cadlab, 'installed', side_effect=ValueError('incomplete')), \
                 patch.object(cadlab, 'defaults', return_value={'branch': 'default', 'commit': 'default-commit', 'repository': 'test-repo'}), \
                 patch.object(cadlab, 'run', side_effect=fake_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    cadlab.install()
            self.assertTrue(any(args[:2] == ('git', 'fetch') and args[-1] == 'selected-commit' for args in calls))
            self.assertTrue(marker.is_file())


if __name__ == '__main__':
    unittest.main()
