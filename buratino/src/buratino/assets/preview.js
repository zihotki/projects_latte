const ui = {
  title: document.getElementById('project-title'),
  dimensions: document.getElementById('project-dimensions'),
  status: document.getElementById('draft-badge'),
  table: document.getElementById('parts-body'),
  caption: document.getElementById('selection-caption'),
  message: document.getElementById('viewer-message'),
  grain: document.getElementById('grain-toggle'),
  drawerPose: document.getElementById('drawer-pose-toggle'),
  visibility: document.getElementById('visibility-options'),
  panelOpacity: document.getElementById('panel-opacity'),
  panelOpacityValue: document.getElementById('panel-opacity-value'),
};

const number = value => Number(value).toLocaleString(undefined, {
  maximumFractionDigits: 1,
});
const dimensionText = dims => `${number(dims.length)} × ${number(dims.width)} × ${number(dims.thickness)} mm`;

let result;
let selectedGroup = null;
let grainVisible = true;
let viewer;
let roleNodes = new Map();
let originalMaterials = new Map();
let highlightedMaterials = new Map();
let outlines = new Map();
let grainMarks = new Map();
let drawerPartNodes = [];
let drawersOpen = false;
let partRoots = new Map();
let visibilityControls = new Map();
let cuttingGroupVisibility = new Map();
let groupByPartId = new Map();
let panelOpacity = 1;

function setMessage(message, isError = false) {
  ui.message.textContent = message;
  ui.message.hidden = !message;
  ui.message.classList.toggle('error', isError);
}

function currentGroup() {
  return result.cutting_groups.find(group => group.id === selectedGroup);
}

function selectGroup(group) {
  selectedGroup = group?.id ?? null;
  for (const row of ui.table.querySelectorAll('tr')) {
    const active = row.dataset.groupId === selectedGroup;
    row.classList.toggle('selected', active);
    row.querySelector('.group-select')?.setAttribute('aria-pressed', String(active));
  }
  applyModelSelection();
  const selected = currentGroup();
  ui.caption.textContent = selected
    ? `${selected.label} · ${selected.quantity} ${selected.quantity === 1 ? 'panel' : 'panels'} · ${selected.material} · ${selected.edge_treatment ?? 'Edge treatment unverified'} · ${selected.grain_status === 'assumed' ? 'Grain direction assumed' : 'Grain direction recorded'}`
    : 'Select a part name or a panel to inspect its cutting blank.';
}

function addCell(row, value, className = '') {
  const cell = document.createElement('td');
  cell.textContent = value;
  if (className) cell.className = className;
  row.appendChild(cell);
}

function renderTable() {
  ui.table.replaceChildren();
  cuttingGroupVisibility = new Map(result.cutting_groups.map(group => [group.id, true]));
  groupByPartId = new Map(result.cutting_groups.flatMap(group =>
    group.members.map(partId => [partId, group])));
  result.cutting_groups.forEach(group => {
    const row = document.createElement('tr');
    row.dataset.groupId = group.id;
    row.title = `${group.label} · ${group.quantity} ${group.quantity === 1 ? 'panel' : 'panels'} · ${group.material}`;
    const dims = group.finished_mm;
    const nameCell = document.createElement('td');
    nameCell.className = 'part-name';
    const select = document.createElement('button');
    select.type = 'button';
    select.className = 'group-select';
    select.textContent = group.label;
    select.setAttribute('aria-pressed', 'false');
    select.addEventListener('click', () => selectGroup(group));
    nameCell.appendChild(select);
    row.appendChild(nameCell);
    addCell(row, String(group.quantity), 'numeric');
    addCell(row, number(dims.length), 'numeric');
    addCell(row, number(dims.width), 'numeric');
    addCell(row, number(dims.thickness), 'numeric');
    addCell(row, group.grain_direction === 'length' ? 'Length*' : '—');
    const visibilityCell = document.createElement('td');
    visibilityCell.className = 'group-visibility-cell';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'group-visibility-toggle';
    toggle.addEventListener('click', () => {
      const visible = cuttingGroupVisibility.get(group.id) === false;
      cuttingGroupVisibility.set(group.id, visible);
      updateGroupVisibilityButton(group, toggle);
      applyPartVisibility();
    });
    updateGroupVisibilityButton(group, toggle);
    visibilityCell.appendChild(toggle);
    row.appendChild(visibilityCell);
    ui.table.appendChild(row);
  });
  selectGroup(null);
}

function updateGroupVisibilityButton(group, button) {
  const visible = cuttingGroupVisibility.get(group.id) !== false;
  button.textContent = visible ? 'Hide' : 'Show';
  button.setAttribute('aria-label', `${visible ? 'Hide' : 'Show'} ${group.label} in model; quantity ${group.quantity}`);
  button.title = `${visible ? 'Hide' : 'Show'} all ${group.quantity} ${group.quantity === 1 ? 'panel' : 'panels'} in the model`;
}

function humanizeProjectName(name) {
  return String(name || 'Bare cabinet')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function roleForNode(node) {
  let current = node;
  while (current) {
    const part = result.parts.find(item => item.role === current.name);
    if (part) return part.role;
    current = current.parent;
  }
  return null;
}

function collectPartNodes() {
  roleNodes = new Map(result.parts.map(part => [part.role, []]));
  partRoots = new Map(result.parts.map(part => [
    part.role, viewer.scene.getObjectByName(part.role),
  ]));
  viewer.scene.traverse(node => {
    if (!node.isMesh) return;
    const role = roleForNode(node);
    if (role) roleNodes.get(role).push(node);
  });
}

function renderVisibilityControls() {
  const parts = result.parts;
  ui.visibility.replaceChildren();
  visibilityControls = new Map();
  const cabinets = result.cabinets?.length
    ? result.cabinets.map(cabinet => ({id: cabinet.id ?? cabinet.name, label: cabinet.name ?? cabinet.id}))
    : [...new Set(parts.map(part => part.cabinet_id ?? 'cabinet'))]
      .map(id => ({id, label: humanizeProjectName(id)}));

  function addToggle(container, key, labelText) {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = true;
    input.dataset.visibilityGroup = key;
    input.addEventListener('change', () => {
      visibilityControls.set(key, input.checked);
      applyPartVisibility();
    });
    label.append(input, document.createTextNode(labelText));
    container.appendChild(label);
    visibilityControls.set(key, true);
  }

  if (result.frames?.length) {
    const section = document.createElement('fieldset');
    section.className = 'visibility-cabinet visibility-frames';
    const heading = document.createElement('legend');
    heading.textContent = 'Frames';
    section.appendChild(heading);
    for (const frame of result.frames) {
      addToggle(section, `frame:${frame.id}`, `${frame.id} frame`);
    }
    ui.visibility.appendChild(section);
  }

  for (const cabinet of cabinets) {
    const partsForCabinet = parts.filter(part => (part.cabinet_id ?? 'cabinet') === cabinet.id);
    const section = document.createElement('fieldset');
    section.className = 'visibility-cabinet';
    const heading = document.createElement('legend');
    heading.textContent = cabinet.label;
    section.appendChild(heading);
    addToggle(section, `cabinet:${cabinet.id}`, cabinet.label);
    const children = document.createElement('div');
    children.className = 'visibility-children';
    addToggle(children, `carcass:${cabinet.id}`, 'Carcass');

    const instances = [...new Set(partsForCabinet
      .map(part => part.instance_id)
      .filter(Boolean))].sort();
    for (const instanceId of instances) {
      const drawer = result.drawers?.find(item => item.instance_id === instanceId);
      addToggle(children, `drawer:${instanceId}`, `Drawer ${drawer?.drawer_index ?? instanceId}`);
    }
    if (partsForCabinet.some(part => part.component === 'face')) {
      addToggle(children, `fronts:${cabinet.id}`, 'Fronts');
    }
    section.appendChild(children);
    ui.visibility.appendChild(section);
  }
}

function applyPartVisibility() {
  for (const part of result.parts) {
    const root = partRoots.get(part.role);
    const cabinetId = part.cabinet_id ?? 'cabinet';
    const instanceId = part.instance_id;
    const cabinetVisible = part.frame_id
      ? visibilityControls.get(`frame:${part.frame_id}`) !== false
      : visibilityControls.get(`cabinet:${cabinetId}`) !== false;
    const subgroupVisible = part.frame_id || (instanceId
      ? visibilityControls.get(`drawer:${instanceId}`) !== false
      : visibilityControls.get(`carcass:${cabinetId}`) !== false);
    const frontVisible = part.component !== 'face' ||
      visibilityControls.get(`fronts:${cabinetId}`) !== false;
    const group = groupByPartId.get(part.id);
    const groupVisible = !group || cuttingGroupVisibility.get(group.id) !== false;
    const visible = cabinetVisible && subgroupVisible && frontVisible && groupVisible;
    if (root) root.visible = visible;
    for (const line of outlines.get(part.role) ?? []) line.visible = visible;
    const mark = grainMarks.get(part.role);
    if (mark) mark.visible = visible && grainVisible;
  }
}

function setPanelOpacity(value) {
  panelOpacity = value;
  ui.panelOpacityValue.textContent = `${Math.round(value * 100)}%`;
  for (const meshes of roleNodes.values()) {
    for (const mesh of meshes) {
      const materials = [originalMaterials.get(mesh), highlightedMaterials.get(mesh)]
        .filter(Boolean)
        .flat();
      for (const material of materials) {
        material.opacity = value;
        material.transparent = value < 1;
        material.depthWrite = value === 1;
        material.needsUpdate = true;
      }
    }
  }
}

function addPartOverlays() {
  const {THREE} = viewer;
  for (const [role, meshes] of roleNodes) {
    const edgeLines = [];
    for (const mesh of meshes) {
      if (!mesh.geometry) continue;
      mesh.receiveShadow = false;
      const geometry = new THREE.EdgesGeometry(mesh.geometry, 20);
      const line = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
        color: 0x344153,
        transparent: true,
        opacity: 0.67,
        depthTest: true,
      }));
      line.name = `cabinet-outline-${role}`;
      line.position.copy(mesh.position);
      line.quaternion.copy(mesh.quaternion);
      line.scale.copy(mesh.scale);
      line.renderOrder = 3;
      mesh.parent.add(line);
      edgeLines.push(line);
      originalMaterials.set(mesh, mesh.material);
    }
    outlines.set(role, edgeLines);
    const mark = createGrainMark(role, meshes);
    if (mark) grainMarks.set(role, mark);
  }
}

function createGrainMark(role, meshes) {
  const part = result.parts.find(item => item.role === role);
  if (!part || !meshes.length || part.grain_axis_local == null) return null;
  const {THREE} = viewer;
  let partNode = meshes[0];
  while (partNode.parent && partNode.name !== role) partNode = partNode.parent;
  if (partNode.name !== role) partNode = meshes[0].parent;
  if (!partNode) return null;
  partNode.updateWorldMatrix(true, false);
  const worldToPart = partNode.matrixWorld.clone().invert();
  const bounds = new THREE.Box3();
  for (const mesh of meshes) {
    mesh.updateWorldMatrix(true, false);
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    const relative = worldToPart.clone().multiply(mesh.matrixWorld);
    bounds.union(mesh.geometry.boundingBox.clone().applyMatrix4(relative));
  }
  if (bounds.isEmpty()) return null;
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const grainAxis = new THREE.Vector3();
  if (['x', 'y', 'z'].includes(part.grain_axis_local)) {
    grainAxis[part.grain_axis_local] = 1;
  } else {
    grainAxis.z = 1;
  }
  const normal = part.surface_normal_axis_local ?? (
    role === 'top' || role === 'bottom' ? 'z'
      : role === 'back' ? 'y' : 'x'
  );
  const planeAxes = ['x', 'y', 'z'].filter(axis => axis !== normal);
  const orientation = {u: planeAxes[0], v: planeAxes[1], normal};
  const dimensions = {x: size.x, y: size.y, z: size.z};
  const uLength = dimensions[orientation.u];
  const vLength = dimensions[orientation.v];
  const directionU = grainAxis[orientation.u];
  const directionV = grainAxis[orientation.v];
  const projectedLength = Math.hypot(directionU, directionV);
  if (projectedLength < 0.01) return null;
  const du = directionU / projectedLength;
  const dv = directionV / projectedLength;
  const nu = -dv;
  const nv = du;
  const uMin = bounds.min[orientation.u];
  const vMin = bounds.min[orientation.v];
  const normalMid = center[orientation.normal];
  const normalOffset = Math.max(0.35, dimensions[orientation.normal] / 2 + 0.4);
  const hatchVertices = [];
  const hatchReach = (Math.abs(nu) * uLength + Math.abs(nv) * vLength) / 2;
  const spacing = Math.max(15, Math.min(22, Math.min(uLength, vLength) / 18));

  function pointOnFace(u, v, faceNormal) {
    const point = new THREE.Vector3();
    point[orientation.u] = u;
    point[orientation.v] = v;
    point[orientation.normal] = faceNormal;
    return point;
  }

  function lineAcrossFace(offset, faceNormal) {
    const originU = uMin + uLength / 2 + nu * offset;
    const originV = vMin + vLength / 2 + nv * offset;
    let tMin = -Infinity;
    let tMax = Infinity;
    for (const [origin, delta, min, length] of [
      [originU, du, uMin, uLength],
      [originV, dv, vMin, vLength],
    ]) {
      const max = min + length;
      if (Math.abs(delta) < 1e-6) {
        if (origin < min || origin > max) return null;
        continue;
      }
      const first = (min - origin) / delta;
      const second = (max - origin) / delta;
      tMin = Math.max(tMin, Math.min(first, second));
      tMax = Math.min(tMax, Math.max(first, second));
    }
    if (tMin > tMax) return null;
    return [
      pointOnFace(originU + du * tMin, originV + dv * tMin, faceNormal),
      pointOnFace(originU + du * tMax, originV + dv * tMax, faceNormal),
    ];
  }

  const arrowVertices = [];
  const arrowLength = Math.min(220, Math.max(150, Math.min(uLength, vLength) * 0.56));
  const arrowHead = Math.min(22, arrowLength * 0.14);
  for (const faceSide of [-1, 1]) {
    const faceNormal = normalMid + faceSide * normalOffset;
    for (let offset = -hatchReach; offset <= hatchReach; offset += spacing) {
      const segment = lineAcrossFace(offset, faceNormal);
      if (segment) hatchVertices.push(...segment);
    }
    const segment = lineAcrossFace(0, faceNormal);
    if (!segment) continue;
    const [start, end] = segment;
    const length = start.distanceTo(end);
    const centerOffset = Math.max(0, (length - arrowLength) / 2);
    const arrowStart = start.clone();
    const arrowDirection = end.clone().sub(start).normalize();
    arrowStart.addScaledVector(arrowDirection, centerOffset);
    const actualLength = Math.min(length, arrowLength);
    const arrowEnd = arrowStart.clone().addScaledVector(arrowDirection, actualLength);
    const across = new THREE.Vector3();
    across[orientation.u] = nu;
    across[orientation.v] = nv;
    arrowVertices.push(
      arrowStart, arrowEnd,
      arrowEnd, arrowEnd.clone().addScaledVector(arrowDirection, -arrowHead).addScaledVector(across, arrowHead * 0.55),
      arrowEnd, arrowEnd.clone().addScaledVector(arrowDirection, -arrowHead).addScaledVector(across, -arrowHead * 0.55),
    );
  }

  const mark = new THREE.Group();
  const hatchGeometry = new THREE.BufferGeometry().setFromPoints(hatchVertices);
  const hatches = new THREE.LineSegments(hatchGeometry, new THREE.LineBasicMaterial({
    color: 0x597c70,
    depthTest: true,
    depthWrite: false,
    transparent: true,
    opacity: 0.42,
  }));
  hatches.name = `grain-hatching-${role}`;
  mark.add(hatches);
  const arrowGeometry = new THREE.BufferGeometry().setFromPoints(arrowVertices);
  const arrows = new THREE.LineSegments(arrowGeometry, new THREE.LineBasicMaterial({
    color: 0x126c5e,
    depthTest: true,
    depthWrite: false,
    transparent: true,
    opacity: 0.98,
  }));
  arrows.name = `grain-direction-arrow-${role}`;
  mark.add(arrows);
  mark.name = `grain-direction-${role}`;
  mark.renderOrder = 6;
  partNode.add(mark);
  mark.visible = grainVisible;
  return mark;
}

function applyModelSelection() {
  const active = currentGroup();
  const memberRoles = new Set(result.parts
    .filter(part => active?.members.includes(part.id))
    .map(part => part.role));
  for (const [role, meshes] of roleNodes) {
    const selected = memberRoles.has(role);
    for (const mesh of meshes) {
      const original = originalMaterials.get(mesh);
      if (!original) continue;
      let highlighted = highlightedMaterials.get(mesh);
      if (!highlighted) {
        const highlight = material => {
          const copy = material.clone();
          if (copy.color) copy.color.set(0x8fbfb2);
          if (copy.emissive) {
            copy.emissive.set(0x173c35);
            copy.emissiveIntensity = 0.18;
          }
          return copy;
        };
        highlighted = Array.isArray(original) ? original.map(highlight) : highlight(original);
        highlightedMaterials.set(mesh, highlighted);
      }
      mesh.material = selected ? highlighted : original;
    }
    for (const line of outlines.get(role) ?? []) {
      line.material.color.set(selected ? 0x24685f : 0x344153);
      line.material.opacity = selected ? 1 : 0.67;
    }
  }
}

function isEffectivelyVisible(node) {
  for (let current = node; current; current = current.parent) {
    if (!current.visible) return false;
    if (current === viewer.scene) break;
  }
  return true;
}

function hasVisibleMaterial(node) {
  if (!node.isMesh) return true;
  const materials = Array.isArray(node.material) ? node.material : [node.material];
  return materials.some(material => material && material.visible !== false && material.opacity > 0);
}

function fitViewer() {
  if (!viewer) return;
  const canvas = viewer.renderer.domElement;
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(bounds.width));
  const height = Math.max(1, Math.floor(bounds.height));
  viewer.renderer.setSize(width, height, false);
  viewer.camera.aspect = width / height;
  viewer.camera.updateProjectionMatrix();
}

function collectDrawerPartNodes() {
  const seen = new Set();
  drawerPartNodes = result.parts
    .filter(part => part.instance_id && !seen.has(part.role) && seen.add(part.role))
    .map(part => ({part, node: viewer.scene.getObjectByName(part.role)}))
    .filter(item => item.node)
    .map(({part, node}) => ({part, node, closedY: node.position.y}));
  ui.drawerPose.hidden = drawerPartNodes.length === 0;
  if (drawerPartNodes.length) setDrawerPose(false);
}

function drawerPoseDistance(part) {
  const drawer = result.drawers?.find(item => item.instance_id === part.instance_id);
  const drawerDepth = Number(drawer?.box_mm?.depth);
  if (Number.isFinite(drawerDepth) && drawerDepth > 0) {
    return {distance: drawerDepth, basis: 'nominal drawer depth'};
  }
  return {
    distance: Number(result.drawer_layout?.display_open_distance_mm) || 0,
    basis: 'fallback display distance',
  };
}

function setDrawerPose(open) {
  drawersOpen = open;
  const distances = drawerPartNodes.map(({part}) => drawerPoseDistance(part));
  const descriptions = [...new Set(distances.map(({distance, basis}) =>
    `${number(distance)} mm ${basis}`))];
  // These named groups keep CadQuery's native axes beneath the rotated GLTF root.
  for (const {part, node, closedY} of drawerPartNodes) {
    const {distance} = drawerPoseDistance(part);
    node.position.y = closedY - (open ? distance : 0);
  }
  ui.drawerPose.textContent = open ? 'Drawers open' : 'Drawers closed';
  const distancesText = descriptions.join(', ');
  const caveat = 'Illustrative pose only; actual runner stroke and full-extension travel are unverified.';
  ui.drawerPose.title = `Open pose uses ${distancesText}. ${caveat}`;
  ui.drawerPose.setAttribute('aria-label', `${ui.drawerPose.textContent}. ${ui.drawerPose.title}`);
  ui.drawerPose.setAttribute('aria-pressed', String(open));
}

function setStandardView(name) {
  const model = viewer.scene.getObjectByName('base_cabinet');
  const box = new viewer.THREE.Box3().setFromObject(model ?? viewer.scene);
  const center = box.getCenter(new viewer.THREE.Vector3());
  const size = box.getSize(new viewer.THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z) * 2.35;
  const directions = {
    front: new viewer.THREE.Vector3(0, 0, 1),
    side: new viewer.THREE.Vector3(1, 0, 0),
    top: new viewer.THREE.Vector3(0, 1, 0),
    iso: new viewer.THREE.Vector3(1, 0.9, 1).normalize(),
  };
  viewer.camera.up.set(0, 1, 0);
  if (name === 'top') viewer.camera.up.set(0, 0, -1);
  viewer.controls.target.copy(center);
  viewer.camera.position.copy(center).addScaledVector(directions[name] ?? directions.iso, radius);
  viewer.camera.lookAt(center);
  viewer.controls.update();
}

async function loadData() {
  try {
    const response = await fetch('./result.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`result.json returned ${response.status}`);
    result = await response.json();
    if (!Array.isArray(result.parts) || !Array.isArray(result.cutting_groups)) {
      throw new Error('The calculation does not include the expected part table.');
    }
    const dims = result.overall_dimensions_mm ?? result.dimensions_mm;
    ui.title.textContent = humanizeProjectName(result.name);
    ui.dimensions.textContent = dims
      ? `${number(dims.width)} W × ${number(dims.height)} H × ${number(dims.depth)} D mm overall`
      : 'Cabinet dimensions unavailable';
    renderTable();
    const panelCount = result.cutting_groups.reduce((sum, group) => sum + group.quantity, 0);
    document.getElementById('group-count').textContent =
      `${result.cutting_groups.length} groups · ${panelCount} panels`;
  } catch (error) {
    setMessage(`Could not load the part list: ${error.message}`, true);
    return false;
  }
  return true;
}

async function waitForViewer() {
  const started = Date.now();
  while (Date.now() - started < 10000) {
    const candidate = window.cabineteerViewer;
    if (candidate?.renderer?.domElement && candidate.scene.getObjectByName('base_cabinet')) {
      viewer = candidate;
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return false;
}

async function refreshStatus() {
  try {
    const response = await fetch('./status.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('status unavailable');
    const {status} = await response.json();
    ui.status.textContent = status === 'current'
      ? 'DRAFT · NOT FOR MANUFACTURING'
      : `${String(status).toUpperCase()} INPUTS · Previous draft shown`;
    ui.status.dataset.state = status;
  } catch {
    ui.status.textContent = 'DRAFT SNAPSHOT · NOT FOR MANUFACTURING';
    ui.status.dataset.state = 'unknown';
  }
}

async function start() {
  if (!await loadData()) return;
  await refreshStatus();
  setInterval(refreshStatus, 3000);
  if (!await waitForViewer()) {
    setMessage('The model did not finish loading. Refresh the preview to try again.', true);
    return;
  }
  collectPartNodes();
  renderVisibilityControls();
  addPartOverlays();
  applyPartVisibility();
  collectDrawerPartNodes();
  for (const light of viewer.scene.children) {
    if (light.isDirectionalLight && light.castShadow) {
      light.shadow.bias = -0.0002;
      light.shadow.normalBias = 0.45;
      light.shadow.needsUpdate = true;
    }
  }
  fitViewer();
  window.addEventListener('resize', fitViewer);
  setStandardView('iso');
  applyModelSelection();
  setPanelOpacity(panelOpacity);
  setMessage('');

  const down = new Map();
  viewer.renderer.domElement.addEventListener('pointerdown', event => {
    down.set(event.pointerId, [event.clientX, event.clientY]);
  });
  viewer.renderer.domElement.addEventListener('pointerup', event => {
    const point = down.get(event.pointerId);
    down.delete(event.pointerId);
    if (!point || Math.hypot(event.clientX - point[0], event.clientY - point[1]) > 5) return;
    const bounds = viewer.renderer.domElement.getBoundingClientRect();
    const pointer = new viewer.THREE.Vector2(
      (event.clientX - bounds.left) / bounds.width * 2 - 1,
      -(event.clientY - bounds.top) / bounds.height * 2 + 1,
    );
    const ray = new viewer.THREE.Raycaster();
    ray.setFromCamera(pointer, viewer.camera);
    for (const hit of ray.intersectObjects(viewer.scene.children, true)) {
      if (hit.object.name.startsWith('cabinet-outline-') ||
          hit.object.name.startsWith('grain-') ||
          !isEffectivelyVisible(hit.object) ||
          !hasVisibleMaterial(hit.object)) continue;
      const role = roleForNode(hit.object);
      if (!role) continue;
      const part = result.parts.find(item => item.role === role);
      const group = result.cutting_groups.find(item => item.members.includes(part?.id));
      if (group) selectGroup(group);
      return;
    }
  });
}

for (const button of document.querySelectorAll('[data-view]')) {
  button.addEventListener('click', () => viewer && setStandardView(button.dataset.view));
}
ui.grain.addEventListener('click', () => {
  grainVisible = !grainVisible;
  ui.grain.setAttribute('aria-pressed', String(grainVisible));
  ui.grain.textContent = grainVisible ? 'Grain marks on' : 'Grain marks off';
  applyPartVisibility();
});
ui.drawerPose?.addEventListener('click', () => {
  if (viewer && drawerPartNodes.length) setDrawerPose(!drawersOpen);
});
ui.panelOpacity?.addEventListener('input', () => {
  setPanelOpacity(Number(ui.panelOpacity.value) / 100);
});

window.addEventListener('keydown', event => {
  const key = event.key.toLowerCase();
  if (!['x', 'v', 'o', 'm', 'c'].includes(key)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}, true);

start();
