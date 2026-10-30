"""Component recipes use the stock-only paired operation resolver."""

import pytest

from cabineteer.joinery import DominoJoinery
from cabineteer.layout import CabinetRef, Row
from cabineteer.operations import DominoRow
from cabineteer.project import CabinetProject, SpaceModelSpec, project_from_dict, project_to_dict
from cabineteer.spaces import (
    AssemblyModule, AssemblyRef, Carcass, Divider, DrawerBox, Fr, Insets,
    Space, SpaceCabinetDefinition, Split, resolve_model,
)


def cuts(model):
    return [operation for part in model.part_plan.parts for operation in part['operations']
            if operation['source'] == 'joint']


def host(carcass=None, root=None, **kwargs):
    return CabinetProject(name='recipe', space_model=SpaceModelSpec(
        carcass or Carcass(600, 700, 560, joinery=DominoJoinery()), root or Space('inside')), **kwargs)


def test_opt_in_recipe_depth_assignment_and_resize():
    assert not cuts(resolve_model(Carcass(600, 700, 560), Space('inside')))
    recipe = DominoJoinery(face_depth=10, end_depth=26, end_offsets=(70, 74))
    model = resolve_model(Carcass(600, 700, 560, joinery=recipe), Space('inside'))
    assert len(cuts(model)) == 16
    for part in model.part_plan.parts:
        for op in part['operations']:
            expected = 10 if op['face'][0] == 'xyz'[part['stock']['thickness_axis']] else 26
            assert op['depth'] == expected
    resized = resolve_model(Carcass(800, 900, 660, joinery=recipe), Space('inside'))
    assert {op['u'] for op in cuts(resized)} >= {70, 580}
    assert {op['u'] for op in cuts(model)} >= {70, 480}


def divider_root(divider):
    return Space('inside', split=Split('height', (
        Space('lower', Fr()), divider, Space('upper', Fr()))))


def test_short_rail_fallback_disable_override_and_adjustable():
    root = divider_root(Divider('rail', depth=50))
    model = host(root=root).resolved_space_model()
    rail = next(part for part in model.part_plan.parts if part['kind'] == 'divider')
    assert len(rail['operations']) == 2
    assert {op['u'] for op in rail['operations']} == {25}
    for divider in (Divider('rail', joinery=None), Divider('rail', role='adjustable')):
        assert len(cuts(host(root=divider_root(divider)).resolved_space_model())) == 16
    with pytest.raises(ValueError, match="adjustable divider cannot have fixed joinery"):
        host(root=divider_root(Divider("shelf", role="adjustable", joinery=DominoJoinery()))).resolved_space_model()
    explicit = Divider('rail', joinery=DominoJoinery(end_offsets=(30, 40)))
    overridden = host(carcass=Carcass(600, 700, 560), root=divider_root(explicit)).resolved_space_model()
    assert len(cuts(overridden)) == 8


def test_divider_to_divider_and_bare_host_boundaries_are_excluded():
    root = Space('inside', split=Split('width', (
        Space('left', Fr(), split=Split('height', (
            Space('bottom', Fr()), Divider('shelf'), Space('top', Fr())))),
        Divider('upright'), Space('right', Fr()))))
    model = host(root=root).resolved_space_model()
    owned = [contact for contact in model.part_plan.contacts if contact.get('joinery')]
    assert all('/carcass/' in contact['part_a'] or '/carcass/' in contact['part_b'] for contact in owned)
    module = AssemblyModule('insert', divider_root(Divider('rail', joinery=DominoJoinery())), Fr(), Fr(), Fr())
    model = host(root=Space('inside', content=AssemblyRef('nested', 'insert')), space_modules=(module,)).resolved_space_model()
    assert len(cuts(model)) == 16


def test_drawer_corners_and_unsupported_geometry():
    recipe = DominoJoinery(end_offsets=(60, 60))
    model = host(carcass=Carcass(600, 700, 560), root=Space('inside', content=DrawerBox(
        'drawer', 30, height=270, corner_joinery=recipe))).resolved_space_model()
    assert len(cuts(model)) == 16
    assert {op['v'] for op in cuts(model)} == {60, 210}
    with pytest.raises(ValueError, match='requires butt'):
        host(root=Space('inside', content=DrawerBox('drawer', 30, joinery_style='qqq', corner_joinery=recipe))).resolved_space_model()


def test_two_instances_and_nested_drawer_keep_unique_local_operations():
    definition = SpaceCabinetDefinition('unit', Carcass(600, 700, 560, joinery=DominoJoinery()), Space('inside'))
    project = CabinetProject(name='row', layout=Row('run', (CabinetRef('a', 'unit'), CabinetRef('b', 'unit'))), space_cabinets=(definition,))
    model = project.resolved_space_assembly()
    assert len(cuts(model)) == 32
    assert len({op['id'] for op in cuts(model)}) == 32
    assert all(contact['part_a'].split('/')[2] == contact['part_b'].split('/')[2] for contact in model.part_plan.contacts)
    drawer_root = Space('insert', content=DrawerBox('drawer', 30, height=270, corner_joinery=DominoJoinery(end_offsets=(60, 60))))
    module = AssemblyModule('insert', drawer_root, Fr(), Fr(), Fr())
    model = host(root=Space('inside', content=AssemblyRef('nested', 'insert', Insets(left=10, front=20))), space_modules=(module,)).resolved_space_model()
    drawer = [op for op in cuts(model) if '/nested/' in op['part_id']]
    assert len(drawer) == 16
    assert {op['v'] for op in drawer} == {60, 210}
    assert all(op['id'].startswith('joint/component-') for op in drawer)


def test_explicit_joint_ownership_collision():
    joint = DominoRow('custom', '/cabinet/carcass/side_left', 'x+',
                      '/cabinet/carcass/bottom', 'x-', (100,), 'y', 20, 6, 12, 28)
    with pytest.raises(ValueError, match='conflicting joint ownership'):
        host(joints=(joint,)).resolved_space_model()
    assert len(cuts(host(carcass=Carcass(600, 700, 560), joints=(joint,)).resolved_space_model())) == 2


@pytest.mark.parametrize('recipe,match', [
    (DominoJoinery(face_depth=18), 'blind mortise'),
    (DominoJoinery(slot_width=20), 'slot does not fit'),
    (DominoJoinery(slot_length=600), 'slot does not fit'),
])
def test_stock_fit_rejects_recipe_without_changing_it(recipe, match):
    with pytest.raises(ValueError, match=match):
        host(carcass=Carcass(600, 700, 560, joinery=recipe)).resolved_space_model()


@pytest.mark.parametrize('kwargs', [
    {'slot_length': float('nan')}, {'slot_width': 0}, {'face_depth': True},
    {'end_offsets': (1,)}, {'end_offsets': (float('inf'), 1)}, {'end_offsets': (-1, 1)},
])
def test_invalid_recipe(kwargs):
    with pytest.raises(ValueError, match='DominoJoinery'):
        DominoJoinery(**kwargs)


def test_round_trip_and_invalid_inherit():
    project = host(root=divider_root(Divider('rail', depth=50)))
    encoded = project_to_dict(project)
    restored = project_from_dict(encoded)
    assert project_to_dict(restored) == encoded
    assert cuts(restored.resolved_space_model()) == cuts(project.resolved_space_model())
    with pytest.raises(ValueError, match='expected DominoJoinery'):
        host(root=divider_root(Divider('rail', joinery='other'))).resolved_space_model()
    with pytest.raises(ValueError, match='expected DominoJoinery'):
        host(carcass=Carcass(600, 700, 560, joinery='inherit')).resolved_space_model()


def test_mcp_schema_exposes_recipe_and_inherit():
    from cabineteer.server import _space_model_schema
    schema = _space_model_schema()
    carcass = schema['properties']['carcass']['properties']['joinery']['oneOf'][1]
    assert carcass['properties']['type'] == {'const': 'DominoJoinery'}
    assert carcass['properties']['end_offsets']['default'] == [50, 50]
    divider = schema['properties']['root']['properties']['split']['properties']['children']['items']['properties']['joinery']
    assert {'const': 'inherit'} in divider['oneOf']
