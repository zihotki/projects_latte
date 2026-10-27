const ui = {
  title: document.getElementById('project-title'),
  dimensions: document.getElementById('project-dimensions'),
  status: document.getElementById('draft-badge'),
  table: document.getElementById('parts-body'),
  tableHint: document.getElementById('table-hint'),
  caption: document.getElementById('selection-caption'),
  message: document.getElementById('viewer-message'),
  drawerPose: document.getElementById('drawer-pose-toggle'),
  doorPose: document.getElementById('door-pose-toggle'),
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
let legacyDrawerPose = false;
let doorPartNodes = [];
let doorsOpen = false;
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
  if (group) document.getElementById('parts-tab')?.click();
  for (const row of ui.table.querySelectorAll('tr')) {
    const active = row.dataset.groupId === selectedGroup;
    row.classList.toggle('selected', active);
    row.querySelector('.group-select')?.setAttribute('aria-pressed', String(active));
  }
  applyModelSelection();
  const selected = currentGroup();
  const memberProfiles = selected?.member_details
    ?.map(member => `${member.label}${member.profile ? ` · ${profileLabel(member.profile)}` : ''}`)
    .filter(Boolean);
  ui.caption.textContent = selected
    ? `${selected.label} · ${selected.quantity} ${selected.quantity === 1 ? 'panel' : 'panels'} · ${selected.material} · ${selected.edge_treatment ?? 'Edge treatment unverified'}${selected.grain_status === 'confirmed' ? '' : ' · Grain direction unverified'} · Blank dimensions only; profile is not a machining instruction${memberProfiles?.length ? ` · Members: ${[...new Set(memberProfiles)].join('; ')}` : ''}`
    : 'Select a part name or a panel to inspect its cutting blank.';
}

function profileLabel(profile) {
  if (typeof profile === 'string') return profile;
  if (!profile || typeof profile !== 'object') return 'profile recorded';
  if (profile.label || profile.name || profile.shape) {
    return profile.label ?? profile.name ?? profile.shape;
  }
  const pointCount = profile.points_mm?.length ?? profile.points?.length;
  return `${profile.plane ? `${profile.plane.toUpperCase()} ` : ''}profile${pointCount ? ` (${pointCount} points)` : ''}`;
}

function addCell(row, value, className = '') {
  const cell = document.createElement('td');
  cell.textContent = value;
  if (className) cell.className = className;
  row.appendChild(cell);
}

function hasAssumedGrain(group) {
  return group.grain_status === 'assumed' ||
    (group.member_details ?? []).some(member => member.grain_status === 'assumed');
}

function renderTable() {
  ui.table.replaceChildren();
  ui.tableHint.textContent = result.cutting_groups.some(hasAssumedGrain)
    ? 'Equal blanks are grouped. * Grain direction is assumed.'
    : 'Equal blanks are grouped.';
  cuttingGroupVisibility = new Map(result.cutting_groups.map(group => [group.id, true]));
  groupByPartId = new Map(result.cutting_groups.flatMap(group =>
    group.members.map(partId => [partId, group])));
  result.cutting_groups.forEach(group => {
    const row = document.createElement('tr');
    row.dataset.groupId = group.id;
    const details = group.member_details ?? [];
    const profileLabels = details
      .filter(member => member.profile)
      .map(member => `${member.label}: ${profileLabel(member.profile)}`);
    row.title = `${group.label} · ${group.quantity} ${group.quantity === 1 ? 'panel' : 'panels'} · ${group.material}${profileLabels.length ? ` · ${[...new Set(profileLabels)].join('; ')}` : ''} · Profile machining unverified`;
    const dims = group.blank_mm ?? group.finished_mm;
    const nameCell = document.createElement('td');
    nameCell.className = 'part-name';
    const select = document.createElement('button');
    select.type = 'button';
    select.className = 'group-select';
    select.textContent = group.label;
    select.setAttribute('aria-pressed', 'false');
    select.addEventListener('click', () => selectGroup(group));
    nameCell.appendChild(select);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'group-visibility-toggle';
    toggle.addEventListener('click', event => {
      event.stopPropagation();
      const visible = cuttingGroupVisibility.get(group.id) === false;
      cuttingGroupVisibility.set(group.id, visible);
      updateGroupVisibilityButton(group, toggle);
      applyPartVisibility();
    });
    updateGroupVisibilityButton(group, toggle);
    nameCell.appendChild(toggle);
    row.appendChild(nameCell);
    addCell(row, String(group.quantity), 'numeric');
    addCell(row, `${number(dims.length)} × ${number(dims.width)} × ${number(dims.thickness)}`);
    row.addEventListener('click', () => selectGroup(group));
    ui.table.appendChild(row);
  });
  selectGroup(null);
}

function updateGroupVisibilityButton(group, button) {
  const visible = cuttingGroupVisibility.get(group.id) !== false;
  button.textContent = visible ? '−' : '+';
  button.setAttribute('aria-label', `${visible ? 'Hide' : 'Show'} ${group.label} in model; quantity ${group.quantity}`);
  button.title = `${visible ? 'Hide' : 'Show'} all ${group.quantity} ${group.quantity === 1 ? 'panel' : 'panels'} in the model`;
}

function humanizeProjectName(name) {
  return String(name || 'Bare cabinet')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function nodeMatchesRole(name, role) {
  const value = String(name || '');
  const target = String(role || '');
  const sanitize = viewer?.THREE?.PropertyBinding?.sanitizeNodeName;
  const clean = candidate => sanitize
    ? sanitize(String(candidate || ''))
    : String(candidate || '').replace(/[.\/:\[\]]/g, '').replace(/\s/g, '_');
  const canonical = value
    .replace(/_part(?:_\d+)?$/, '')
    .replace(/_\d+$/, '');
  return value === target || clean(value) === clean(target) || canonical === target ||
    clean(canonical) === clean(target) ||
    value.startsWith(`${target}_part`) || value.startsWith(`${target}_`);
}

function partNode(part) {
  const role = part.role ?? part.viewer_role ?? part.id;
  const exact = viewer.scene.getObjectByName(role);
  if (exact) return exact;
  let match = null;
  viewer.scene.traverse(node => {
    if (!nodeMatchesRole(node.name, role)) return;
    if (!match || (!node.isMesh && match.isMesh)) match = node;
  });
  return match;
}

function roleForNode(node) {
  let current = node;
  while (current) {
    const part = result.parts.find(item => nodeMatchesRole(
      current.name, item.role ?? item.viewer_role ?? item.id,
    ));
    if (part) return part.role;
    current = current.parent;
  }
  return null;
}

function collectPartNodes() {
  roleNodes = new Map(result.parts.map(part => [part.role, []]));
  partRoots = new Map(result.parts.map(part => [
    part.role, partNode(part),
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

  function addToggle(container, key, labelText, accessibleName = labelText) {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.setAttribute('aria-label', accessibleName);
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

  const upperGroups = [...new Set(parts.map(part => part.upper_id).filter(Boolean))];
  if (upperGroups.length) {
    const section = document.createElement('fieldset');
    section.className = 'visibility-cabinet visibility-frames';
    const heading = document.createElement('legend');
    heading.textContent = 'Upper panels';
    section.appendChild(heading);
    const labels = {left: 'Left upper', right: 'Right upper', shared: 'Shared top'};
    for (const upperId of ['left', 'right', 'shared']) {
      if (upperGroups.includes(upperId)) {
        addToggle(section, `upper:${upperId}`, labels[upperId] ?? humanizeProjectName(upperId));
      }
    }
    for (const upperId of upperGroups.filter(id => !['left', 'right', 'shared'].includes(id))) {
      addToggle(section, `upper:${upperId}`, humanizeProjectName(upperId));
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
    const cabinetLabel = humanizeProjectName(cabinet.label);
    addToggle(section, `cabinet:${cabinet.id}`, cabinetLabel);
    const children = document.createElement('div');
    children.className = 'visibility-children';
    addToggle(children, `carcass:${cabinet.id}`, 'Carcass');

    const instances = [...new Set(partsForCabinet
      .map(part => part.instance_id)
      .filter(Boolean))].sort();
    for (const instanceId of instances) {
      const drawer = result.drawers?.find(item => item.instance_id === instanceId);
      const drawerNumber = drawer?.drawer_index ?? instanceId;
      addToggle(children, `drawer:${instanceId}`, `D${drawerNumber}`, `Drawer ${drawerNumber}`);
    }
    if (partsForCabinet.some(part => ['face', 'door', 'drawer_front'].includes(part.component))) {
      addToggle(children, `fronts:${cabinet.id}`, 'Fronts');
    }
    const individual = document.createElement('details');
    individual.className = 'part-visibility';
    const summary = document.createElement('summary');
    summary.textContent = 'Individual parts';
    individual.appendChild(summary);
    for (const part of partsForCabinet) {
      addToggle(individual, `part:${part.id}`, part.label ?? part.component ?? part.id);
    }
    children.appendChild(individual);
    section.appendChild(children);
    ui.visibility.appendChild(section);
  }
}

function applyPartVisibility() {
  for (const part of result.parts) {
    const root = partRoots.get(part.role);
    const cabinetId = part.cabinet_id ?? 'cabinet';
    const instanceId = part.instance_id;
    const cabinetVisible = part.upper_id
      ? visibilityControls.get(`upper:${part.upper_id}`) !== false
      : part.frame_id
        ? visibilityControls.get(`frame:${part.frame_id}`) !== false
        : visibilityControls.get(`cabinet:${cabinetId}`) !== false;
    const subgroupVisible = part.upper_id || part.frame_id || (instanceId
      ? visibilityControls.get(`drawer:${instanceId}`) !== false
      : visibilityControls.get(`carcass:${cabinetId}`) !== false);
    const frontVisible = !['face', 'door', 'drawer_front'].includes(part.component) ||
      visibilityControls.get(`fronts:${cabinetId}`) !== false;
    const group = groupByPartId.get(part.id);
    const groupVisible = !group || cuttingGroupVisibility.get(group.id) !== false;
    const visible = cabinetVisible && subgroupVisible && frontVisible && groupVisible;
    const partVisible = visibilityControls.get(`part:${part.id}`) !== false;
    if (root) root.visible = visible && partVisible;
    for (const line of outlines.get(part.role) ?? []) line.visible = visible && partVisible;
    const mark = grainMarks.get(part.role);
    if (mark) mark.visible = visible && partVisible && grainVisible;
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

function createProfileGrainMark(role, part, meshes, partNode) {
  const {THREE} = viewer;
  const axisNames = ['x', 'y', 'z'];
  const grainAxis = part.grain_axis_local;
  const normalAxis = part.surface_normal_axis_local;
  if (!axisNames.includes(grainAxis) || !axisNames.includes(normalAxis) || grainAxis === normalAxis) {
    return null;
  }

  partNode.updateWorldMatrix(true, false);
  const worldToPart = partNode.matrixWorld.clone().invert();
  const expectedNormal = new THREE.Vector3();
  expectedNormal[normalAxis] = 1;
  if (normalAxis === 'z' && Array.isArray(part.profile?.points_mm)) {
    const points = part.profile.points_mm;
    let broadEdge = null;
    for (let i = 0; i < points.length; i += 1) {
      const start = points[i];
      const end = points[(i + 1) % points.length];
      const dx = end[0] - start[0];
      const dz = end[1] - start[1];
      if (!broadEdge || Math.abs(dx) > Math.abs(broadEdge.dx)) broadEdge = {dx, dz};
    }
    if (broadEdge && Math.abs(broadEdge.dx) > 1e-7) {
      expectedNormal.set(-broadEdge.dz, 0, broadEdge.dx).normalize();
    }
  }
  const grainDirection = new THREE.Vector3();
  grainDirection[grainAxis] = 1;
  const surfaces = [];

  for (const mesh of meshes) {
    if (!mesh.geometry) continue;
    mesh.updateWorldMatrix(true, false);
    const geometry = mesh.geometry;
    const positions = geometry.attributes.position;
    if (!positions) continue;
    const relative = worldToPart.clone().multiply(mesh.matrixWorld);
    const index = geometry.index;
    const vertexCount = index ? index.count : positions.count;
    for (let triangle = 0; triangle < Math.floor(vertexCount / 3); triangle += 1) {
      const vertices = [];
      for (let corner = 0; corner < 3; corner += 1) {
        const item = triangle * 3 + corner;
        const vertexIndex = index ? index.getX(item) : item;
        vertices.push(new THREE.Vector3().fromBufferAttribute(positions, vertexIndex).applyMatrix4(relative));
      }
      const faceNormal = vertices[1].clone().sub(vertices[0])
        .cross(vertices[2].clone().sub(vertices[0])).normalize();
      if (Math.abs(faceNormal.dot(expectedNormal)) < 0.9999) continue;
      const surfaceGrain = grainDirection.clone()
        .addScaledVector(faceNormal, -grainDirection.dot(faceNormal));
      if (surfaceGrain.lengthSq() < 1e-10) continue;
      surfaceGrain.normalize();
      const surfaceAcross = faceNormal.clone().cross(surfaceGrain).normalize();
      const plane = faceNormal.dot(vertices[0]);
      let surface = surfaces.find(item => item.normal.dot(faceNormal) > 0.9999 &&
        Math.abs(item.plane - plane) < 0.02);
      if (!surface) {
        surface = {
          normal: faceNormal,
          grain: surfaceGrain,
          across: surfaceAcross,
          plane,
          triangles: [],
          acrossMin: Infinity,
          acrossMax: -Infinity,
          grainMin: Infinity,
          grainMax: -Infinity,
        };
        surfaces.push(surface);
      }
      const projectedTriangle = vertices.map(vertex => ({
        grain: vertex.dot(surface.grain),
        across: vertex.dot(surface.across),
      }));
      for (const point of projectedTriangle) {
        surface.acrossMin = Math.min(surface.acrossMin, point.across);
        surface.acrossMax = Math.max(surface.acrossMax, point.across);
        surface.grainMin = Math.min(surface.grainMin, point.grain);
        surface.grainMax = Math.max(surface.grainMax, point.grain);
      }
      surface.triangles.push(projectedTriangle);
    }
  }

  function mergeIntervals(intervals) {
    intervals.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const interval of intervals) {
      const last = merged[merged.length - 1];
      if (last && interval[0] <= last[1] + 0.01) last[1] = Math.max(last[1], interval[1]);
      else merged.push(interval.slice());
    }
    return merged;
  }

  function intervalsAt(surface, across) {
    const intervals = [];
    for (const triangle of surface.triangles) {
      const crossings = [];
      for (let edge = 0; edge < 3; edge += 1) {
        const start = triangle[edge];
        const end = triangle[(edge + 1) % 3];
        if (across < Math.min(start.across, end.across) - 1e-7 ||
            across > Math.max(start.across, end.across) + 1e-7) continue;
        if (Math.abs(start.across - end.across) < 1e-7) {
          if (Math.abs(across - start.across) < 1e-7) crossings.push(start.grain, end.grain);
          continue;
        }
        const t = (across - start.across) / (end.across - start.across);
        if (t >= -1e-7 && t <= 1 + 1e-7) {
          crossings.push(start.grain + (end.grain - start.grain) * t);
        }
      }
      if (crossings.length >= 2) {
        const low = Math.min(...crossings);
        const high = Math.max(...crossings);
        if (high - low > 0.01) intervals.push([low, high]);
      }
    }
    return mergeIntervals(intervals);
  }

  function pointOnFace(surface, grain, across) {
    return surface.grain.clone().multiplyScalar(grain)
      .addScaledVector(surface.across, across)
      .addScaledVector(surface.normal, surface.plane + 0.4);
  }

  const hatchVertices = [];
  const arrowVertices = [];
  for (const surface of surfaces) {
    const acrossLength = surface.acrossMax - surface.acrossMin;
    const grainLength = surface.grainMax - surface.grainMin;
    if (acrossLength <= 0 || grainLength <= 0) continue;
    const spacing = Math.max(15, Math.min(22, Math.min(acrossLength, grainLength) / 18));
    for (let across = surface.acrossMin + spacing / 2;
      across < surface.acrossMax; across += spacing) {
      for (const [start, end] of intervalsAt(surface, across)) {
        hatchVertices.push(pointOnFace(surface, start, across), pointOnFace(surface, end, across));
      }
    }

    const centerAcross = (surface.acrossMin + surface.acrossMax) / 2;
    const centerIntervals = intervalsAt(surface, centerAcross);
    const longest = centerIntervals.sort((a, b) => (b[1] - b[0]) - (a[1] - a[0]))[0];
    if (!longest) continue;
    const length = longest[1] - longest[0];
    const arrowLength = Math.min(length, 220, Math.max(150, Math.min(acrossLength, grainLength) * 0.56));
    const arrowHead = Math.min(22, arrowLength * 0.14);
    const start = (longest[0] + longest[1] - arrowLength) / 2;
    const end = start + arrowLength;
    const tip = pointOnFace(surface, end, centerAcross);
    const base = pointOnFace(surface, end - arrowHead, centerAcross);
    const left = base.clone().addScaledVector(surface.across, arrowHead * 0.55);
    const right = base.clone().addScaledVector(surface.across, -arrowHead * 0.55);
    arrowVertices.push(pointOnFace(surface, start, centerAcross), tip, tip, left, tip, right);
  }

  return createGrainMarkGroup(role, partNode, hatchVertices, arrowVertices);
}

function createGrainMarkGroup(role, partNode, hatchVertices, arrowVertices) {
  const {THREE} = viewer;
  if (!hatchVertices.length) return null;
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

function createGrainMark(role, meshes) {
  const part = result.parts.find(item => item.role === role);
  if (!part || !meshes.length || part.grain_axis_local == null) return null;
  const {THREE} = viewer;
  let partNode = meshes[0];
  while (partNode.parent && partNode.name !== role) partNode = partNode.parent;
  if (partNode.name !== role) partNode = meshes[0].parent;
  if (!partNode) return null;
  if (part.profile) return createProfileGrainMark(role, part, meshes, partNode);
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

  return createGrainMarkGroup(role, partNode, hatchVertices, arrowVertices);
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
    .map(part => ({part, node: partNode(part)}))
    .filter(item => item.node)
    .map(({part, node}) => ({part, node, closedY: node.position.y}));
  let hasLegacyDrawer = false;
  viewer.scene.traverse(node => { hasLegacyDrawer ||= /^bay\d+_drawer\d+/.test(node.name); });
  legacyDrawerPose = drawerPartNodes.length === 0 &&
    typeof viewer.setDrawerState === 'function' && hasLegacyDrawer;
  ui.drawerPose.hidden = drawerPartNodes.length === 0 && !legacyDrawerPose;
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
  if (legacyDrawerPose) {
    viewer.setDrawerState(open ? 2 : 0);
    ui.drawerPose.title = 'Legacy native drawer animation. Illustrative pose only; actual runner stroke and full-extension travel are unverified.';
    ui.drawerPose.textContent = open ? 'Close drawers' : 'Open drawers';
    ui.drawerPose.setAttribute('aria-label', ui.drawerPose.title);
    ui.drawerPose.setAttribute('aria-pressed', String(open));
    return;
  }
  const distances = drawerPartNodes.map(({part}) => drawerPoseDistance(part));
  const descriptions = [...new Set(distances.map(({distance, basis}) =>
    `${number(distance)} mm ${basis}`))];
  // These named groups keep CadQuery's native axes beneath the rotated GLTF root.
  for (const {part, node, closedY} of drawerPartNodes) {
    const {distance} = drawerPoseDistance(part);
    node.position.y = closedY - (open ? distance : 0);
  }
  const distancesText = descriptions.join(', ');
  const caveat = 'Illustrative pose only; actual runner stroke and full-extension travel are unverified.';
  ui.drawerPose.title = `Open pose uses ${distancesText}. ${caveat}`;
  ui.drawerPose.textContent = open ? 'Close drawers' : 'Open drawers';
  ui.drawerPose.setAttribute('aria-label', `${ui.drawerPose.textContent}. ${ui.drawerPose.title}`);
  ui.drawerPose.setAttribute('aria-pressed', String(open));
}

function collectDoorPartNodes() {
  doorPartNodes = result.parts
    .filter(part => part.component === 'door' && ['right', 'left'].includes(part.hinge_side))
    .map(part => ({part, node: partNode(part)}))
    .filter(item => item.node)
    .map(({part, node}) => {
      node.updateWorldMatrix(true, false);
      const bounds = new viewer.THREE.Box3().setFromObject(node);
      const pivot = new viewer.THREE.Vector3(
        part.hinge_side === 'right' ? bounds.max.x : bounds.min.x,
        (bounds.min.y + bounds.max.y) / 2,
        bounds.max.z,
      );
      part.preview_pivot_mm = pivot.toArray();
      const pivotNode = new viewer.THREE.Object3D();
      viewer.scene.add(pivotNode);
      pivotNode.position.copy(pivot);
      pivotNode.attach(node);
      return {part, node, pivotNode, sign: part.hinge_side === 'right' ? 1 : -1};
    });
  ui.doorPose.hidden = doorPartNodes.length === 0;
  if (doorPartNodes.length) setDoorPose(false);
}

function setDoorPose(open) {
  doorsOpen = open;
  const angle = open ? Math.PI * 75 / 180 : 0;
  for (const {pivotNode, sign} of doorPartNodes) {
    pivotNode.rotation.y = sign * angle;
  }
  const assumed = doorPartNodes.some(({part}) => part.hinge_side_status === 'assumed_for_preview');
  const caveat = `${assumed ? 'Right edge is a preview assumption; hinge side is unverified. ' : ''}Illustrative 75° swing. Hardware, clearances, and actual travel are unverified.`;
  ui.doorPose.title = caveat;
  ui.doorPose.textContent = open ? 'Close doors' : 'Open doors';
  ui.doorPose.setAttribute('aria-label', `${ui.doorPose.textContent}. ${caveat}`);
  ui.doorPose.setAttribute('aria-pressed', String(open));
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
    if (window.cabinetViewerData?.parts) result = window.cabinetViewerData;
    else {
      const response = await fetch('./result.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`result.json returned ${response.status}`);
      result = await response.json();
    }
    result.parts = (result.parts ?? []).map(part => ({
      ...part,
      role: part.role ?? part.viewer_role ?? part.id,
      cabinet_id: part.cabinet_id ?? part.owner ?? 'cabinet',
      label: part.label ?? part.component ?? part.id,
      finished_mm: part.finished_mm ?? part.stock_mm ?? {length: 0, width: 0, thickness: 0},
    }));
    result.cutting_groups ??= result.parts.map(part => ({
      id: `part:${part.id}`, label: part.label, quantity: part.quantity ?? 1,
      material: part.material ?? 'material unknown', members: [part.id],
      blank_mm: part.blank_mm ?? part.finished_mm,
    }));
    result.cabinets ??= [...new Set(result.parts.map(part => part.cabinet_id))]
      .map(id => ({id, name: id}));
    const dims = result.overall_dimensions_mm ?? result.dimensions_mm;
    ui.title.textContent = result.title ?? humanizeProjectName(result.name ?? 'Cabinet');
    ui.dimensions.textContent = dims
      ? `${number(dims.width)} W × ${number(dims.height)} H × ${number(dims.depth)} D mm overall`
      : 'Cabinet dimensions unavailable';
    renderTable();
    const panelCount = result.cutting_groups.reduce((sum, group) => sum + group.quantity, 0);
    document.getElementById('group-count').textContent =
      `${result.cutting_groups.length} groups · ${panelCount} panels`;
    const links = result.viewer_links ?? {};
    for (const [id, href] of [['report-link', links.report], ['cutlist-link', links.cutlist]]) {
      const link = document.getElementById(id);
      if (href) { link.href = href; link.hidden = false; }
    }
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
    const hasNamedModel = candidate?.scene.getObjectByName('base_cabinet');
    const hasMetadataModel = result?.parts?.some(part =>
      candidate?.scene.getObjectByName(part.role ?? part.viewer_role ?? part.id));
    const loaded = document.getElementById('loading')?.style.display === 'none';
    if (candidate?.renderer?.domElement && (hasNamedModel || hasMetadataModel || loaded)) {
      viewer = candidate;
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return false;
}

async function refreshStatus() {
  try {
    if (result?.draft_status) {
      ui.status.textContent = result.draft_status;
      ui.status.dataset.state = result.draft_state ?? 'draft';
      return;
    }
    const response = await fetch('./status.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('status unavailable');
    const {status} = await response.json();
    ui.status.textContent = status === 'current'
      ? 'DRAFT · NOT FOR MANUFACTURING'
      : `${String(status).toUpperCase()} INPUTS · Old draft`;
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
  collectDoorPartNodes();
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
function selectSheetTab(tab) {
  const panes = { 'tree-tab': 'tree-view', 'parts-tab': 'parts-view', 'settings-tab': 'settings-view' };
  for (const [buttonId, paneId] of Object.entries(panes)) {
    document.getElementById(buttonId).setAttribute('aria-selected', String(buttonId === tab));
    document.getElementById(paneId).hidden = buttonId !== tab;
  }
  document.getElementById('sheet-title').textContent = { 'tree-tab': 'Model', 'parts-tab': 'Parts', 'settings-tab': 'Settings' }[tab];
  document.body.classList.add('sheet-open');
  document.getElementById('sheet-toggle').setAttribute('aria-expanded', 'true');
}
for (const tab of ['tree-tab', 'parts-tab', 'settings-tab']) {
  document.getElementById(tab)?.addEventListener('click', () => selectSheetTab(tab));
}
document.getElementById('sheet-toggle')?.addEventListener('click', event => {
  const open = document.body.classList.toggle('sheet-open');
  event.currentTarget.setAttribute('aria-expanded', String(open));
});
document.getElementById('show-all')?.addEventListener('click', () => {
  for (const key of visibilityControls.keys()) visibilityControls.set(key, true);
  document.querySelectorAll('#visibility-options input').forEach(input => { input.checked = true; });
  for (const group of result.cutting_groups) cuttingGroupVisibility.set(group.id, true);
  document.querySelectorAll('.group-visibility-toggle').forEach((button, index) => {
    updateGroupVisibilityButton(result.cutting_groups[index], button);
  });
  applyPartVisibility();
});
document.getElementById('isolate-selection')?.addEventListener('click', () => {
  const group = currentGroup();
  if (!group) return;
  for (const key of visibilityControls.keys()) visibilityControls.set(key, true);
  document.querySelectorAll('#visibility-options input').forEach(input => { input.checked = true; });
  for (const part of result.parts) visibilityControls.set(`part:${part.id}`, group.members.includes(part.id));
  document.querySelectorAll('#visibility-options input').forEach(input => {
    if (input.dataset.visibilityGroup?.startsWith('part:')) {
      input.checked = visibilityControls.get(input.dataset.visibilityGroup) !== false;
    }
  });
  for (const item of result.cutting_groups) cuttingGroupVisibility.set(item.id, item.id === group.id);
  document.querySelectorAll('.group-visibility-toggle').forEach((button, index) => {
    updateGroupVisibilityButton(result.cutting_groups[index], button);
  });
  applyPartVisibility();
});
document.getElementById('reset-selection')?.addEventListener('click', () => {
  document.getElementById('show-all')?.click();
  selectGroup(null);
});
ui.drawerPose?.addEventListener('click', () => {
  if (viewer && drawerPartNodes.length) setDrawerPose(!drawersOpen);
});
ui.doorPose?.addEventListener('click', () => {
  if (viewer && doorPartNodes.length) setDoorPose(!doorsOpen);
});
ui.panelOpacity?.addEventListener('input', () => {
  setPanelOpacity(Number(ui.panelOpacity.value) / 100);
});

start();
