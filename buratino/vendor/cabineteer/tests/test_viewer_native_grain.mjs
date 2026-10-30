import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import * as THREE from '../../../vendor/three/build/three.module.js';
import {GLTFLoader} from '../../../vendor/three/examples/jsm/loaders/GLTFLoader.js';

const [glbPath, metadataPath] = process.argv.slice(2);
const parts = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
const data = fs.readFileSync(glbPath);
const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
const model = (await new GLTFLoader().parseAsync(buffer, '')).scene;
assert.equal(model.children.length, 1);
const cadRoot = model.children[0];
const scene = new THREE.Scene();
scene.add(model);
model.position.y = 73;

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(here, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const body = source.slice(source.indexOf('function createProfileGrainMark('), source.indexOf('function applyModelSelection('));
const context = {
  viewer: {THREE, cadRoot}, grainVisible: true,
  result: {parts}, partRoots: new Map(),
};
vm.createContext(context);
vm.runInContext(body, context);

function pointInTriangle(point, triangle) {
  const [a, b, c] = triangle.vertices;
  const cross = (u, v, w) => (v.x - u.x) * (w.y - u.y) - (v.y - u.y) * (w.x - u.x);
  const sign = Math.sign(cross(a, b, c));
  return sign !== 0 && [[a, b], [b, c], [c, a]].every(([u, v]) =>
    sign * cross(u, v, point) >= -0.05);
}

for (const part of parts) {
  const node = model.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(part.role));
  assert.ok(node, `missing part node ${part.role}`);
  context.partRoots.set(part.role, node);
  const meshes = [];
  node.traverse(child => { if (child.isMesh) meshes.push(child); });
  assert.ok(meshes.length);
  const frame = context.stockFrameTriangles(part, meshes, node);
  assert.ok(frame && frame.triangles.length, `${part.role}: no stock triangles`);
  const faces = context.selectStockMainFaceTriangles(frame.triangles, 'z', frame.size);
  assert.ok(faces.length, `${part.role}: no stock main faces`);
  const mark = context.createGrainMark(part.role, meshes);
  assert.ok(mark, `${part.role}: no grain mark`);
  assert.equal(mark.children.length, 1, `${part.role}: the grain mark contains hatches only`);
  assert.equal(mark.children[0].name, `grain-hatching-${part.role}`);
  const toStock = frame.stockToPart.clone().invert();
  for (const segment of mark.children) {
    const positions = segment.geometry.attributes.position;
    assert.ok(positions.count, `${part.role}: no hatch vertices`);
    for (let i = 0; i < positions.count; i += 1) {
      const point = new THREE.Vector3().fromBufferAttribute(positions, i).applyMatrix4(toStock);
      assert.ok([0, frame.size[2]].some(plane => Math.abs(Math.abs(point.z - plane) - 0.4) < 0.03),
        `${part.role}: mark is not above an original main face`);
      assert.ok(faces.some(face => pointInTriangle(point, face)),
        `${part.role}: mark leaves the actual face boundary`);
    }
  }
  const firstPoint = new THREE.Vector3().fromBufferAttribute(mark.children[0].geometry.attributes.position, 0);
  const before = mark.localToWorld(firstPoint.clone());
  node.position.y -= 27;
  const after = mark.localToWorld(firstPoint.clone());
  assert.ok(Math.abs(after.distanceTo(before) - 27) < 1e-6,
    `${part.role}: mark does not follow the opening pose`);
}
console.log(`native grain marks checked on ${parts.length} actual GLB parts`);
