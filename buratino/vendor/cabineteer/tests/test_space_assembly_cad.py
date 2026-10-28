from types import SimpleNamespace

import pytest

pytest.importorskip('cadquery')

from cabineteer.layout import CabinetRef, Frame, Row, Stack
from cabineteer.space_adapter import materialize_model, validate_model
from cabineteer.space_assembly import resolve_space_assembly
from cabineteer.spaces import AppliedFaceboard, Carcass, Door, Fixed, Fr, Space, SpaceCabinetDefinition, Split


def test_two_cabinets_and_frame_materialize_from_plan():
    left = SpaceCabinetDefinition('left', Carcass(Fr(), 720, 560), Space('inside'), (Door('door', 'inside', hinge_side='left'),))
    right_root = Space('inside', split=Split('height', (Space('lower', Fr()), Space('upper', Fr()))))
    right = SpaceCabinetDefinition('right', Carcass(Fr(), 720, 560), right_root, (Door('door', 'upper', hinge_side='right'), AppliedFaceboard('board', 'lower')))
    row = Row('row', (CabinetRef('a', 'left'), CabinetRef('b', 'right')), size_x=Fixed(1440))
    stack = Stack('stack', (row, Frame('frame', 1440, 560, 100, 30)))
    project = SimpleNamespace(layout=stack, space_model=None, space_cabinets=(left, right), space_modules=())
    plan = resolve_space_assembly(project)
    shapes = materialize_model(plan)
    assert set(shapes) == {part['id'] for part in plan.part_plan.parts}
    assert validate_model(plan, shapes=shapes) == {'status': 'passed', 'diagnostics': []}
