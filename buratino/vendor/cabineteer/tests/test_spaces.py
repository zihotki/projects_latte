import json
import subprocess
import sys

import pytest

from cabineteer.spaces import (
    AppliedDrawerFront, Carcass, Divider, Door, DrawerBox, Fixed, Fr,
    ResolvedModel, Space, Split, resolve_model,
)


def model(children, height=900, edge=None, fronts=()):
    return resolve_model(Carcass(600, height + 36, 550),
                         Space('root', split=Split('height', children, edge)), fronts)


def heights(result):
    return [s['size'][2] for s in result.spaces[1:]]


def test_budget_and_nested_dividers():
    r = model([Space('a', Fixed(240)), Space('b', Fixed(240)), Divider('s', role='adjustable'), Space('c', Fr())])
    assert heights(r) == [240, 240, 402]
    assert r.dividers[0]['origin'][1] == 3
    assert sum(p['id'] == '/root/s' for p in r.part_plan.parts) == 1
    r = model([Space('a', Fr()), Space('b', Fr()), Divider('s'), Space('c', Fixed(300))])
    assert heights(r) == [291, 291, 300]
    r = model([Space('lower', Fixed(400), Split('height', [Space('a', Fixed(100)), Divider('inner'), Space('b', Fr())])), Divider('outer'), Space('upper', Fr())])
    assert heights(r) == [400, 100, 282, 482]
    assert {d['id'] for d in r.dividers} == {'/root/lower/inner', '/root/outer'}


def test_short_divider_is_a_front_rail_without_back_contact():
    r = model([Space('lower', Fr()), Divider('rail', depth=50), Space('upper', Fr())])
    rail = next(p for p in r.part_plan.parts if p['id'] == '/root/rail')
    assert rail['origin'][1] == 0
    assert rail['size'] == [564, 50, 18]
    pairs = {frozenset((c['part_a'], c['part_b'])) for c in r.part_plan.contacts}
    assert frozenset(('/root/rail', '/carcass/side_left')) in pairs
    assert frozenset(('/root/rail', '/carcass/side_right')) in pairs
    assert frozenset(('/root/rail', '/carcass/back')) not in pairs
    recessed = model([Space('lower', Fr()), Divider('rail', recess=7, depth=50), Space('upper', Fr())])
    assert recessed.dividers[0]['origin'][1] == 7


@pytest.mark.parametrize('depth', [0, -1, float('nan'), float('inf'), 545])
def test_invalid_divider_depth(depth):
    with pytest.raises(ValueError, match='depth'):
        model([Space('lower', Fr()), Divider('rail', depth=depth), Space('upper', Fr())])


def test_remainders_and_edges():
    r = model([Space('a', Fr()), Space('b', Fr()), Space('c', Fr())], 200, 'bottom')
    assert heights(r) == [66, 66, 66]
    assert r.allowances[0]['size'][2] == 2
    assert r.spaces[1]['origin'][2] == 20
    r = model([Space('a', Fr(1)), Space('b', Fr(2))], 100)
    assert heights(r) == [33, 66]
    assert r.allowances[0]['edge'] == 'top'
    r = resolve_model(Carcass(236, 136, 550), Space('root', split=Split('width', [Space('a', Fr()), Space('b', Fr()), Space('c', Fr())], 'left')))
    assert [s['size'][0] for s in r.spaces[1:]] == [66,66,66]
    assert r.spaces[1]['origin'][0] == 20


def test_drawer_fit_and_front_relationships():
    children = [Space('a', Fixed(291), content=DrawerBox('box_a', 30)), Space('b', Fixed(291), content=DrawerBox('box_b', 30, 180)), Space('c', Fr())]
    r = model(children, fronts=[Door('door', 'root')])
    assert [c['size'][2] for c in r.contents] == [249,180]
    assert [c['origin'][2] for c in r.contents] == [48,339]
    assert len(r.fronts) == 1 and r.fronts[0]['attached_to'] is None
    fronts = [AppliedDrawerFront('fa', 'a', 'box_a'), AppliedDrawerFront('fb', 'b', 'box_b')]
    r = model(children, fronts=fronts)
    a,b = r.fronts
    assert b['origin'][2] - (a['origin'][2]+a['size'][2]) == 2
    assert a['attached_to'] == '/root/a/box_a'
    assert heights(r) == [291,291,318]
    with pytest.raises(ValueError, match='outside coverage'):
        model(children, fronts=[AppliedDrawerFront('bad', 'a', 'box_b')])


def test_drawer_top_reveal_changes_only_exposed_edge():
    children = [Space('lower', Fr(), content=DrawerBox('lower-box', 30, 270)),
                Divider('rail', depth=50),
                Space('upper', Fr(), content=DrawerBox('upper-box', 30, 270))]
    fronts = [AppliedDrawerFront('lower-front', 'lower', 'lower-box', top_reveal=9),
              AppliedDrawerFront('upper-front', 'upper', 'upper-box', top_reveal=3)]
    result = model(children, height=643, fronts=fronts)
    lower, upper = result.fronts
    assert lower['size'][2] == upper['size'][2] == 336
    assert lower['origin'][2] == 2
    assert upper['origin'][2] - lower['origin'][2] - lower['size'][2] == 2
    assert upper['origin'][2] + upper['size'][2] == 676


@pytest.mark.parametrize('top_reveal', [-1, float('nan'), float('inf')])
def test_invalid_drawer_top_reveal(top_reveal):
    with pytest.raises(ValueError, match='top reveal'):
        model([Space('drawer', Fr(), content=DrawerBox('box', 30, 270))],
              fronts=[AppliedDrawerFront('front', 'drawer', 'box', top_reveal=top_reveal)])


def test_unequal_fronts_and_roundtrip():
    r = model([Space('a', Fixed(240), content=DrawerBox('one',30)), Space('b', Fixed(360), content=DrawerBox('two',30)), Space('rest', Fr())], fronts=[AppliedDrawerFront('fa','a','one'), AppliedDrawerFront('fb','b','two')])
    assert [f['size'][2] for f in r.fronts] == [255,357]
    assert ResolvedModel.from_dict(json.loads(json.dumps(r.to_dict()))).to_dict() == r.to_dict()


@pytest.mark.parametrize('children, message', [
    ([Space('a', Fixed(240.5)), Space('b', Fr())], 'fractional'),
    ([Space('a', Fixed(899))], '1 mm unallocated'),
    ([Space('a', Fixed(901))], 'overfills'),
    ([Space('a', Fr(0))], 'positive integer'),
    ([Space('a', Fixed(900)), Space('b', Fr())], 'zero'),
    ([Space('a', Fr()), Space('a', Fr())], 'duplicate'),
])
def test_invalid(children, message):
    with pytest.raises(ValueError, match=message): model(children)


def test_no_cad_import_in_fresh_process():
    code = '''import json, sys
from cabineteer.spaces import Carcass, Space, resolve_model, ResolvedModel
m = resolve_model(Carcass(600,936,550), Space('root'))
assert ResolvedModel.from_dict(json.loads(json.dumps(m.to_dict()))).to_dict() == m.to_dict()
assert not any(k == 'cadquery' or k.startswith('OCP') for k in sys.modules)
'''
    subprocess.run([sys.executable, '-c', code], check=True)


def test_errors_report_paths_and_drawer_constraints():
    with pytest.raises(ValueError, match='/root/a/box.*does not fit'):
        model([Space('a', Fixed(42), content=DrawerBox('box', 30)), Space('b', Fr())])
    with pytest.raises(ValueError, match='unknown'):
        model([Space('a', Fr())], fronts=[Door('bad', 'missing')])
    nested = [Space('a', Fixed(450), Split('height', [Space('same', Fr())])), Space('b', Fr(), Split('height', [Space('same', Fr())]))]
    with pytest.raises(ValueError, match='ambiguous'):
        model(nested, fronts=[Door('bad', 'same')])
    r = model([Space('a', Fixed(215), content=DrawerBox('legacy', 30, 180)), Space('b', Fr())])
    assert r.contents[0]['size'][2] == 180
    assert r.contents[0]['top_clearance'] == 0


def test_cad_blocked_import_and_resolution():
    code = '''import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'cadquery' or fullname.startswith('OCP'):
            raise AssertionError('unexpected CAD import: ' + fullname)
sys.meta_path.insert(0, Block())
from cabineteer.spaces import Carcass, Space, DrawerBox, resolve_model, ResolvedModel
m = resolve_model(Carcass(600,936,550), Space('root', content=DrawerBox('box',30)))
assert ResolvedModel.from_dict(json.loads(json.dumps(m.to_dict()))).to_dict() == m.to_dict()
'''
    subprocess.run([sys.executable, '-c', code], check=True)


@pytest.mark.parametrize('divider', [[], [Divider('wall')]])
def test_adjacent_doors_share_horizontal_reveal(divider):
    r = resolve_model(Carcass(636, 936, 550), Space('root', split=Split('width', [Space('left', Fr()), *divider, Space('right', Fr())])), [Door('left_door', 'left'), Door('right_door', 'right')])
    left, right = r.fronts
    assert right['origin'][0] - left['origin'][0] - left['size'][0] == 2


@pytest.mark.parametrize('kwargs', [
    {'front_gap': -1}, {'front_gap': float('nan')}, {'side_thickness': -1},
    {'front_back_thickness': 0}, {'bottom_thickness': float('inf')},
    {'bottom_dado_inset': -1}, {'bottom_dado_depth': -1},
    {'side_thickness': 100},
])
def test_invalid_drawer_recipe_and_full_bounds(kwargs):
    with pytest.raises(ValueError, match='/root/box'):
        resolve_model(Carcass(600, 936, 550), Space('root', content=DrawerBox('box', 30, **kwargs)))


def test_generated_part_ids_cannot_collide():
    with pytest.raises(ValueError, match='duplicate part ID /carcass/side_left'):
        resolve_model(Carcass(600, 936, 550), Space('carcass', split=Split('height', [Space('a', Fr()), Divider('side_left'), Space('b', Fr())])))
    with pytest.raises(ValueError, match='duplicate part ID /front/face'):
        resolve_model(Carcass(600, 936, 550), Space('front', split=Split('height', [Space('a', Fr()), Divider('face'), Space('b', Fr())])), [Door('face', 'front')])


def test_contact_intent_and_virtual_boundaries():
    r = resolve_model(Carcass(636, 936, 550), Space('root', split=Split('width', [
        Space('left', Fr(), split=Split('height', [Space('a', Fr(), content=DrawerBox('box',30)), Divider('shelf'), Space('b', Fr())])),
        Divider('wall'), Space('right', Fr())])))
    by_id = {s['id']: s for s in r.spaces}
    assert by_id['/root/left']['boundaries']['right'] == '/root/wall'
    assert by_id['/root/left/a']['boundaries']['top'] == '/root/left/shelf'
    assert by_id['/root/left/b']['boundaries']['bottom'] == '/root/left/shelf'
    pairs = {(c['part_a'], c['part_b'], c['type']) for c in r.part_plan.contacts}
    def has(a, b, kind): return (*sorted((a,b)), kind) in pairs
    assert has('/root/left/shelf', '/root/wall', 'butt')
    assert has('/root/left/shelf', '/carcass/side_left', 'butt')
    assert has('/root/wall', '/carcass/top', 'butt')
    assert has('/root/left/a/box/bottom', '/root/left/a/box/side_L', 'bottom_groove')
    assert has('/root/left/a/box/side_L', '/root/left/a/box/sub_front', 'drawer_corner')
    assert len(pairs) == len(r.part_plan.contacts)
    assert ResolvedModel.from_dict(json.loads(json.dumps(r.to_dict()))).to_dict() == r.to_dict()
    v = model([Space('a', Fr()), Space('b', Fr())], 201)
    assert v.spaces[1]['boundaries']['top'] is None
    assert v.spaces[2]['boundaries']['bottom'] is None
    assert v.spaces[2]['boundaries']['top'] is None  # allowance separates it from the shell


def test_direct_manga_call_loads_cad():
    pytest.importorskip('cadquery')
    code = '''import cadquery as cq
from cabineteer.drawer import DrawerConfig, add_manga_stack
assembly = cq.Assembly()
add_manga_stack(assembly, DrawerConfig(600, 250, 550, use_standard_height=False))
assert len(assembly.children) == 5
'''
    subprocess.run([sys.executable, '-c', code], check=True)
