import shutil
from pathlib import Path

import pytest


@pytest.fixture
def root():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path, root):
    path = tmp_path / "simple-cabinet"
    shutil.copytree(
        root / "projects/simple-cabinet", path, ignore=shutil.ignore_patterns("build")
    )
    return path


@pytest.fixture
def linked_row_project(tmp_path, root):
    path = tmp_path / "linked-row-fixture"
    shutil.copytree(
        root / "projects/linked-row-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    return path


@pytest.fixture
def shared_column_project(tmp_path, root):
    path = tmp_path / "shared-column-fixture"
    shutil.copytree(
        root / "projects/shared-column-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    return path
