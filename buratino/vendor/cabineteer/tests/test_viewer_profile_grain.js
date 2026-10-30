const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const helper = source.slice(source.indexOf('function isOuterProfileFace('), source.indexOf('function createGrainMarkGroup('));
const profileMark = source.slice(source.indexOf('function createProfileGrainMark('), source.indexOf('function isOuterProfileFace('));
const context = {};
vm.createContext(context);
vm.runInContext(helper, context);

const isOuterProfileFace = context.isOuterProfileFace;
const minPlane = 0;
const maxPlane = 18;

assert.equal(isOuterProfileFace(1, maxPlane, minPlane, maxPlane), true, 'keeps the positive outer face');
assert.equal(isOuterProfileFace(-1, minPlane, minPlane, maxPlane), true, 'keeps the opposite outer face');
assert.equal(isOuterProfileFace(1, 16, minPlane, maxPlane), false, 'drops an inset rebate floor');
assert.equal(isOuterProfileFace(-1, 2, minPlane, maxPlane), false, 'drops an inset groove floor');
assert.equal(isOuterProfileFace(0.8, maxPlane, minPlane, maxPlane), false, 'drops a sloped wall');
assert.match(profileMark, /isOuterProfileFace\(normalAlignment, expectedNormal\.dot\(vertices\[0\]\), minPlane, maxPlane\)/);
