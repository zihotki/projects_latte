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

    def test_environment_selects_profile_and_shared_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch.dict('os.environ', {'SOMA_APP': 'other', 'SOMA_APP_TOKEN': 'other'}):
                env = cadlab.environment(project)
            self.assertNotIn('SOMA_APP', env)
            self.assertNotIn('SOMA_APP_TOKEN', env)
            self.assertEqual(env['SOMA_USER_DATA'], str(cadlab.profile_for(project)))
            self.assertEqual(env['SOMA_SHARED_SKILLS_PROJECT'], str(project.resolve()))

    def test_source_checkout_can_be_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / 'python/soma').mkdir(parents=True)
            python = source / '.venv/bin/python'
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(cadlab, 'SOURCE', source), patch.object(cadlab, 'PYTHON', python):
                cadlab.source_ready()


if __name__ == '__main__':
    unittest.main()
