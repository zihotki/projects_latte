import shutil

import pytest

from buratino.preview import input_status
from buratino.project import InputError, input_identity, load_project


def test_project_source_executes_once_in_fresh_worker(root, tmp_path):
    path = tmp_path / "cabinet"
    shutil.copytree(
        root / "projects/simple-cabinet", path, ignore=shutil.ignore_patterns("build")
    )
    marker = tmp_path / "runs.txt"
    with (path / "project.py").open("a", encoding="utf-8") as source:
        source.write(
            "\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('run', encoding='utf-8')\n"
        )

    inputs = load_project(path)

    assert marker.read_text() == "run"
    assert inputs.source_hash
    assert inputs.identity == input_identity(path)
    assert inputs.variables["width_mm"] == 720
    assert inputs.calculated["closed_depth_mm"] == 500
    assert inputs.native_project.name == "simple-cabinet"
    assert inputs.drawer_configs == {}


def test_drawer_configs_keep_native_hardware_calculations_in_parent(root):
    from buratino.drawers import HETTICH_PROFILE, register_eb20_profile

    register_eb20_profile()
    inputs = load_project(root / "projects/drawer-cabinet")
    config = inputs.drawer_configs["cabinet/column-0/opening-0"]

    assert config.slide_key == "buratino_hettich_quadro_v6_eb20"
    assert config.box_width == 676
    assert config.box_depth == 450
    assert config.bottom_dado_inset == 13
    assert HETTICH_PROFILE["bottom_underside_recess_mm"] == {"min": 12, "max": 13}


def test_drawer_config_exports_must_use_native_configs(root, tmp_path):
    path = tmp_path / "cabinet"
    shutil.copytree(
        root / "projects/simple-cabinet", path, ignore=shutil.ignore_patterns("build")
    )
    with (path / "project.py").open("a", encoding="utf-8") as source:
        source.write("\ndrawer_configs = {'cabinet/opening-0': object()}\n")

    with pytest.raises(InputError) as error:
        load_project(path)
    assert error.value.code == "invalid_drawer_configs"


def test_input_identity_hashes_source_without_executing_it(tmp_path):
    path = tmp_path / "cabinet"
    path.mkdir()
    marker = tmp_path / "should-not-run"
    source = path / "project.py"
    source.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('run')\n"
        "not even valid Python syntax (`\n",
        encoding="utf-8",
    )

    first = input_identity(path)
    assert input_status(path, "some-other-identity")["status"] == "stale"

    source.write_text("# edit without running\n", encoding="utf-8")
    assert input_identity(path) != first
    assert not marker.exists()


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("variables = {\n", "project_syntax_error"),
        ("variables = {}\ncalculated = {}\n", "missing_export"),
        (
            "variables = {'bad': float('nan')}\n"
            "calculated = {}\n"
            "from cabineteer.project import CabinetProject\n"
            "project = CabinetProject(name='x', cabinets=())\n",
            "invalid_export",
        ),
    ],
)
def test_invalid_authored_module_returns_structured_error(tmp_path, source, code):
    path = tmp_path / "cabinet"
    path.mkdir()
    (path / "project.py").write_text(source, encoding="utf-8")

    with pytest.raises(InputError) as error:
        load_project(path)
    assert error.value.code == code
