const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const helper = source.slice(source.indexOf('function profileMainFaceRange('), source.indexOf('function createGrainMarkGroup('));
const context = {};
vm.createContext(context);
vm.runInContext(helper, context);

const profileMainFaceRange = context.profileMainFaceRange;
const isOuterProfileFace = context.isOuterProfileFace;
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
