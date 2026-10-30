import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import * as THREE from '../../../vendor/three/build/three.module.js';
import {GLTFLoader} from '../../../vendor/three/examples/jsm/loaders/GLTFLoader.js';

const [glbPath, metadataPath] = process.argv.slice(2);
const part = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
const data = fs.readFileSync(glbPath);
const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
const model = (await new GLTFLoader().parseAsync(buffer, '')).scene;
assert.equal(model.children.length, 1, 'the actual GLB has one CAD basis root');
const cadRoot = model.children[0];
const scene = new THREE.Scene();
scene.add(model);
// Match the production viewer floor adjustment. It must cancel at the CAD root.
model.position.y = 73;
const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(here, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const body = source.slice(source.indexOf('function createProfileGrainMark('), source.indexOf('function applyModelSelection('));
const context = {
  viewer: {THREE, cadRoot}, grainVisible: true,
  result: {parts: [part]}, partRoots: new Map(),
};
vm.createContext(context);
vm.runInContext(body, context);

const partNode = model.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(part.role));
assert.ok(partNode, `missing part node ${part.role}`);
context.partRoots.set(part.role, partNode);
const meshes = [];
partNode.traverse(node => { if (node.isMesh) meshes.push(node); });
assert.ok(meshes.length > 1, 'edge band gives split mesh geometry');
const before = JSON.stringify(part);
const frame = context.stockFrameTriangles(part, meshes, partNode);
assert.ok(frame && frame.triangles.length);
const selected = context.selectStockMainFaceTriangles(
  frame.triangles, part.surface_normal_axis_local, frame.size,
);
assert.ok(selected.length > 0);
const axis = part.surface_normal_axis_local;
const size = frame.size['xyz'.indexOf(axis)];
for (const plane of [0, size]) {
  assert.ok(selected.some(({vertices}) => vertices.every(point => Math.abs(point[axis] - plane) < 0.02)),
    `main face ${plane} selected`);
}
assert.ok(frame.triangles.some(({vertices, normal}) =>
  Math.abs(normal[axis]) > 0.9999 &&
  vertices.every(point => point[axis] > 0.02 && point[axis] < size - 0.02)),
  'the real operation has an inset floor');
assert.ok(selected.every(({vertices}) => vertices.every(point =>
  Math.abs(point[axis]) < 0.02 || Math.abs(point[axis] - size) < 0.02)),
  'inset floors and walls are excluded');
const mark = context.createGrainMark(part.role, meshes);
assert.ok(mark, 'real selected triangles produce a mark');
const toStock = cadRoot.matrixWorld.clone().invert();
const stockOrigin = new THREE.Vector3(...part.transform.translation);
for (const segment of mark.children) {
  const positions = segment.geometry.attributes.position;
  assert.ok(positions.count > 0, 'the mark has hatch and arrow segments');
  for (let item = 0; item < positions.count; item += 1) {
    const point = new THREE.Vector3().fromBufferAttribute(positions, item);
    const stockPoint = mark.localToWorld(point).applyMatrix4(toStock).sub(stockOrigin);
    assert.ok([0, size].some(plane => Math.abs(Math.abs(stockPoint[axis] - plane) - 0.4) < 0.02),
      'every mark vertex is above an original stock face');
    for (const side of 'xyz') {
      if (side === axis) continue;
      const limit = frame.size['xyz'.indexOf(side)];
      assert.ok(stockPoint[side] >= -0.02 && stockPoint[side] <= limit + 0.02,
        'every mark vertex stays within the stock face bounds');
    }
  }
}
const markPoint = new THREE.Vector3().fromBufferAttribute(mark.children[0].geometry.attributes.position, 0);
const firstWorld = mark.localToWorld(markPoint.clone());
partNode.position.y -= 27;
const secondWorld = mark.localToWorld(markPoint.clone());
assert.ok(Math.abs(secondWorld.distanceTo(firstWorld) - 27) < 1e-6, 'mark follows the part pose');
assert.equal(JSON.stringify(part), before, 'viewer does not change manufacturing metadata');
console.log(`stock faces: ${selected.length} of ${frame.triangles.length} triangles; split meshes: ${meshes.length}`);
