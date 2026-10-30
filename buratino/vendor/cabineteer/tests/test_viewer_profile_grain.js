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
  surface_normal_axis_local: 'x',
  stock: {dimensions: [18, 414, 600]},
}, {x: 1, y: 0, z: 0});
assert.deepEqual({...stockRange}, {min: 0, max: 18}, 'uses original stock dimensions when there is no profile outline');
assert.equal(isOuterProfileFace(1, 4, stockRange.min, stockRange.max), false, 'does not mark a pocket floor at the finished mesh extreme');
assert.equal(isOuterProfileFace(-1, 14, stockRange.min, stockRange.max), false, 'does not mark an opposite-side pocket floor');
assert.match(profileMark, /profileMainFaceRange\(part, expectedNormal\)/);
