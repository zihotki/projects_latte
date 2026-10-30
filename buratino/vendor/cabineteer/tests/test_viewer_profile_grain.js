const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const helper = source.slice(source.indexOf('function profileMainFaceRange('), source.indexOf('function createGrainMarkGroup('));
const profileMark = source.slice(source.indexOf('function createProfileGrainMark('), source.indexOf('function profileMainFaceRange('));
const context = {};
vm.createContext(context);
vm.runInContext(helper, context);

const profileMainFaceRange = context.profileMainFaceRange;
const isOuterProfileFace = context.isOuterProfileFace;
const profileRange = profileMainFaceRange({
  surface_normal_axis_local: 'z',
  profile: {points_mm: [[0, 0], [80, 0], [80, 18], [0, 18]]},
}, {x: 0, y: 0, z: 1});
assert.deepEqual({...profileRange}, {min: 0, max: 18}, 'uses the original profile outline');

assert.equal(isOuterProfileFace(1, 18, profileRange.min, profileRange.max), true, 'keeps the positive outer face');
assert.equal(isOuterProfileFace(-1, 0, profileRange.min, profileRange.max), true, 'keeps the opposite outer face');
assert.equal(isOuterProfileFace(1, 3, profileRange.min, profileRange.max), false, 'drops a full-face pocket floor after the original face is removed');
assert.equal(isOuterProfileFace(-1, 15, profileRange.min, profileRange.max), false, 'drops an inset groove floor');
assert.equal(isOuterProfileFace(0.8, 18, profileRange.min, profileRange.max), false, 'drops a sloped wall');

const stockRange = profileMainFaceRange({
  surface_normal_axis_local: 'z',
  origin: [18, 0, 582],
  stock: {dimensions: [684, 414, 18]},
}, {x: 0, y: 0, z: 1});
assert.deepEqual({...stockRange}, {min: 582, max: 600}, 'maps the generated top panel stock planes to its CAD coordinates');
assert.equal(isOuterProfileFace(1, 600, stockRange.min, stockRange.max), true);
assert.equal(isOuterProfileFace(-1, 582, stockRange.min, stockRange.max), true);
assert.equal(isOuterProfileFace(1, 596, stockRange.min, stockRange.max), false, 'does not mark a pocket floor after the positive face is removed');
assert.equal(isOuterProfileFace(-1, 586, stockRange.min, stockRange.max), false, 'does not mark a pocket floor after the negative face is removed');

const sideRange = profileMainFaceRange({
  surface_normal_axis_local: 'x',
  origin: [702, 0, 0],
  stock: {dimensions: [18, 414, 600]},
}, {x: 1, y: 0, z: 0});
assert.deepEqual({...sideRange}, {min: 702, max: 720}, 'maps the generated right-side stock planes to its CAD coordinates');

const upperProfileRange = profileMainFaceRange({
  surface_normal_axis_local: 'x',
  position_mm: {x: 120, y: 0, z: 50},
  profile: {points_mm: [[0, 0], [24, 0], [24, 120], [0, 120]]},
}, {x: 1, y: 0, z: 0});
assert.deepEqual({...upperProfileRange}, {min: 0, max: 24}, 'keeps legacy profile points in their local coordinate frame');

const upperFaceRange = profileMainFaceRange({
  surface_normal_axis_local: 'y',
  position_mm: {x: 120, y: 42, z: 50},
  profile: {plane: 'xz', points_mm: [[0, 0], [24, 0], [24, 120]], extrusion_axis: 'y', extrusion_mm: 18},
}, {x: 0, y: 1, z: 0});
assert.deepEqual({...upperFaceRange}, {min: 0, max: 18}, 'uses local profile extrusion depth');
assert.match(profileMark, /profileMainFaceRange\(part, expectedNormal\)/);
