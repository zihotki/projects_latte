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
let selectedPartIds = new Set();
let selectedLabel = null;
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
  selectedPartIds = new Set(group?.members ?? []);
  selectedLabel = group?.label ?? null;
  if (group) document.getElementById('parts-tab')?.click();
  for (const row of ui.table.querySelectorAll('tr')) {
    const active = row.dataset.groupId === selectedGroup;
    row.classList.toggle('selected', active);
    row.setAttribute('aria-selected', String(active));
  }
  updateTreeSelectionState();
  applyModelSelection();
  const selected = currentGroup();
  const memberProfiles = selected?.member_details
    ?.map(member => `${member.label}${member.profile ? ` · ${profileLabel(member.profile)}` : ''}`)
    .filter(Boolean);
  ui.caption.textContent = selected
    ? `${selected.label} · ${selected.quantity} ${selected.quantity === 1 ? 'panel' : 'panels'} · ${selected.material} · ${selected.edge_treatment ?? 'Edge treatment unverified'}${selected.grain_status === 'confirmed' ? '' : ' · Grain direction unverified'} · Blank dimensions only; profile is not a machining instruction${memberProfiles?.length ? ` · Members: ${[...new Set(memberProfiles)].join('; ')}` : ''}`
    : selectedLabel ? `${selectedLabel} selected.` : 'Select a part or row.';
}

function selectTreeParts(parts, label) {
  selectedPartIds = new Set(parts.map(part => part.id));
  selectedLabel = label;
  selectedGroup = parts.length === 1 ? groupByPartId.get(parts[0].id)?.id ?? null : null;
  for (const row of ui.table.querySelectorAll('tr')) {
    const active = row.dataset.groupId === selectedGroup;
    row.classList.toggle('selected', active);
    row.setAttribute('aria-selected', String(active));
  }
  updateTreeSelectionState();
  applyModelSelection();
  ui.caption.textContent = `${label} selected.`;
}

function updateTreeSelectionState() {
  for (const row of document.querySelectorAll('.tree-owner')) {
    const children = row.nextElementSibling;
    const ids = [...children.querySelectorAll('[data-part-id]')].map(item => item.dataset.partId);
    const selected = ids.length > 0 && ids.every(id => selectedPartIds.has(id));
    row.querySelector('.tree-label').setAttribute('aria-pressed', String(selected));
  }
  for (const row of document.querySelectorAll('.tree-part')) {
    const id = row.dataset.partId;
    row.querySelector('.tree-label').setAttribute('aria-pressed', String(selectedPartIds.has(id)));
  }
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
    row.tabIndex = 0;
    row.setAttribute('aria-selected', 'false');
    const details = group.member_details ?? [];
    const profileLabels = details
      .filter(member => member.profile)
      .map(member => `${member.label}: ${profileLabel(member.profile)}`);
    row.title = `${group.label} · ${group.quantity} ${group.quantity === 1 ? 'panel' : 'panels'} · ${group.material}${profileLabels.length ? ` · ${[...new Set(profileLabels)].join('; ')}` : ''} · Profile machining unverified`;
    const dims = group.blank_mm ?? group.finished_mm;
    const nameCell = document.createElement('td');
    nameCell.className = 'part-name';
    const select = document.createElement('span');
    select.className = 'group-select';
    select.textContent = group.label;
    nameCell.appendChild(select);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'group-visibility-toggle';
    toggle.addEventListener('click', event => {
      event.stopPropagation();
      const visible = cuttingGroupVisibility.get(group.id) === false;
      cuttingGroupVisibility.set(group.id, visible);
      updateGroupVisibilityButton(group, toggle);
      syncVisibilityControls();
      applyPartVisibility();
    });
    updateGroupVisibilityButton(group, toggle);
    nameCell.appendChild(toggle);
    row.appendChild(nameCell);
    addCell(row, String(group.quantity), 'numeric');
    addCell(row, `${number(dims.length)} × ${number(dims.width)} × ${number(dims.thickness)}`);
    row.addEventListener('click', () => selectGroup(group));
    row.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      selectGroup(group);
    });
    ui.table.appendChild(row);
  });
  selectGroup(null);
}

function updateGroupVisibilityButton(group, button) {
  const visible = cuttingGroupVisibility.get(group.id) !== false;
  updateEyeButton(button, visible, false, `${group.label}, ${group.quantity} ${group.quantity === 1 ? 'part' : 'parts'}`);
}

function humanizeProjectName(name) {
  return String(name || 'Bare cabinet')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function friendlyPartLabel(part) {
  const label = String(part.label ?? '').trim();
  const component = String(part.component ?? '').trim();
  const codeLike = !label || label === component || label === part.id ||
    /^[\w.-]+$/.test(label) && /[_.-]/.test(label);
  return humanizeProjectName(codeLike ? component || part.id : label);
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
  const owners = result.cabinets?.length
    ? result.cabinets.map(owner => ({id: owner.id ?? owner.name, label: owner.name ?? owner.id}))
    : [...new Set(parts.map(part => part.cabinet_id ?? 'cabinet'))]
      .map(id => ({id, label: id}));
  const knownOwners = new Set(owners.map(owner => owner.id));
  for (const part of parts) {
    const id = part.cabinet_id ?? 'cabinet';
    if (!knownOwners.has(id)) {
      owners.push({id, label: id});
      knownOwners.add(id);
    }
  }
  const ownerOrder = ['lower', 'upper.left', 'upper.right', 'roof', 'frame.support'];
  owners.sort((left, right) => {
    const leftIndex = ownerOrder.indexOf(String(left.id).toLowerCase().replaceAll('_', '.'));
    const rightIndex = ownerOrder.indexOf(String(right.id).toLowerCase().replaceAll('_', '.'));
    return (leftIndex < 0 ? ownerOrder.length : leftIndex) -
      (rightIndex < 0 ? ownerOrder.length : rightIndex) || ownerLabel(left).localeCompare(ownerLabel(right));
  });
  const partsByOwner = new Map(owners.map(owner => [owner.id, []]));
  for (const part of parts) {
    const ownerId = part.cabinet_id ?? 'cabinet';
    if (!partsByOwner.has(ownerId)) partsByOwner.set(ownerId, []);
    partsByOwner.get(ownerId).push(part);
    visibilityControls.set(`part:${part.id}`, true);
  }

  function ownerLabel(owner) {
    const key = String(owner.id).toLowerCase().replaceAll('_', '.');
    const known = {
      lower: 'Lower',
      'upper.left': 'Upper left',
      'upper.right': 'Upper right',
      roof: 'Roof',
      'frame.support': 'Support frame',
    };
    return known[key] ?? humanizeProjectName(owner.label);
  }

  for (const owner of owners) {
    const ownerParts = partsByOwner.get(owner.id) ?? [];
    const row = document.createElement('div');
    row.className = 'tree-row tree-owner';
    row.setAttribute('role', 'treeitem');
    row.setAttribute('aria-expanded', 'false');
    const disclosure = document.createElement('button');
    disclosure.type = 'button';
    disclosure.className = 'tree-disclosure';
    disclosure.setAttribute('aria-label', `Expand ${ownerLabel(owner)}`);
    disclosure.textContent = '›';
    const label = document.createElement('button');
    label.type = 'button';
    label.className = 'tree-label';
    label.textContent = ownerLabel(owner);
    label.dataset.selectionKey = `owner:${owner.id}`;
    label.setAttribute('aria-pressed', 'false');
    label.addEventListener('click', () => selectTreeParts(ownerParts, label.textContent));
    disclosure.addEventListener('click', () => {
      const expanded = row.getAttribute('aria-expanded') !== 'true';
      row.setAttribute('aria-expanded', String(expanded));
      disclosure.setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} ${ownerLabel(owner)}`);
      disclosure.textContent = expanded ? '⌄' : '›';
      children.hidden = !expanded;
    });
    const eye = makeEyeButton(`Hide ${ownerLabel(owner)}`, true, false);
    eye.addEventListener('click', () => {
      const allVisible = ownerParts.every(isPartVisible);
      const nextVisible = !allVisible;
      for (const part of ownerParts) visibilityControls.set(`part:${part.id}`, nextVisible);
      if (nextVisible) {
        for (const part of ownerParts) {
          const group = groupByPartId.get(part.id);
          if (group) cuttingGroupVisibility.set(group.id, true);
        }
      }
      syncGroupVisibilityButtons();
      syncVisibilityControls();
      applyPartVisibility();
    });
    row.append(disclosure, label, eye);
    ui.visibility.appendChild(row);

    const children = document.createElement('div');
    children.className = 'tree-children';
    children.setAttribute('role', 'group');
    children.hidden = true;
    const labelCounts = new Map();
    for (const part of ownerParts) {
      const baseLabel = friendlyPartLabel(part);
      labelCounts.set(baseLabel, (labelCounts.get(baseLabel) ?? 0) + 1);
    }
    const seenLabels = new Map();
    for (const part of ownerParts) {
      const baseLabel = friendlyPartLabel(part);
      const ordinal = (seenLabels.get(baseLabel) ?? 0) + 1;
      seenLabels.set(baseLabel, ordinal);
      const partLabel = labelCounts.get(baseLabel) > 1 ? `${baseLabel} ${ordinal}` : baseLabel;
      const childRow = document.createElement('div');
      childRow.className = 'tree-row tree-part';
      childRow.dataset.partId = part.id;
      childRow.setAttribute('role', 'treeitem');
      const spacer = document.createElement('span');
      spacer.className = 'tree-spacer';
      const partButton = document.createElement('button');
      partButton.type = 'button';
      partButton.className = 'tree-label';
      partButton.textContent = partLabel;
      partButton.dataset.selectionKey = `part:${part.id}`;
      partButton.setAttribute('aria-pressed', 'false');
      partButton.addEventListener('click', () => selectTreeParts([part], partLabel));
      const partEye = makeEyeButton(`Hide ${partLabel}`, true, false);
      partEye.addEventListener('click', () => {
        const key = `part:${part.id}`;
        const nextVisible = !isPartVisible(part);
        visibilityControls.set(key, nextVisible);
        const group = groupByPartId.get(part.id);
        if (nextVisible && group) cuttingGroupVisibility.set(group.id, true);
        syncGroupVisibilityButtons();
        syncVisibilityControls();
        applyPartVisibility();
      });
      childRow.append(spacer, partButton, partEye);
      children.appendChild(childRow);
    }
    ui.visibility.appendChild(children);
  }
  document.getElementById('group-count').textContent = `${parts.length} parts`;
  syncVisibilityControls();
}

function makeEyeButton(label, visible, mixed) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'tree-eye';
  button.setAttribute('aria-label', label);
  updateEyeButton(button, visible, mixed, label);
  return button;
}

function updateEyeButton(button, visible, mixed, label) {
  const eye = '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>';
  const slash = '<path d="m4 4 16 16"/>';
  button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${eye}${visible && !mixed ? '' : slash}</svg>`;
  button.setAttribute('aria-pressed', mixed ? 'mixed' : String(visible));
  button.classList.toggle('mixed', mixed);
  button.classList.toggle('hidden-part', !visible && !mixed);
  button.title = mixed ? `Some ${label.replace(/^Hide /, '')} parts are hidden. Show all.` : `${visible ? 'Hide' : 'Show'} ${label.replace(/^Hide /, '')}`;
  button.setAttribute('aria-label', mixed
    ? `Some ${label.replace(/^Hide /, '')} parts hidden; show all`
    : `${visible ? 'Hide' : 'Show'} ${label.replace(/^Hide /, '')}`);
}

function syncVisibilityControls() {
  for (const row of document.querySelectorAll('.tree-owner')) {
    const children = row.nextElementSibling;
    const inputs = [...children.querySelectorAll('[data-part-id]')];
    const states = inputs.map(item => {
      const part = result.parts.find(candidate => candidate.id === item.dataset.partId);
      return part ? isPartVisible(part) : false;
    });
    const allVisible = states.every(Boolean);
    const allHidden = states.every(state => !state);
    updateEyeButton(row.querySelector('.tree-eye'), allVisible, !allVisible && !allHidden, `Hide ${row.querySelector('.tree-label').textContent}`);
    for (const item of inputs) {
      const part = result.parts.find(candidate => candidate.id === item.dataset.partId);
      const visible = part ? isPartVisible(part) : false;
      item.classList.toggle('hidden-part', !visible);
    }
  }
  for (const part of result.parts) {
    const row = [...document.querySelectorAll('.tree-part')]
      .find(item => item.querySelector('.tree-label')?.dataset.selectionKey === `part:${part.id}`);
    if (!row) continue;
    const visible = isPartVisible(part);
    const label = row.querySelector('.tree-label').textContent;
    updateEyeButton(row.querySelector('.tree-eye'), visible, false, `Hide ${label}`);
    row.classList.toggle('hidden-part', !visible);
  }
}

function isPartVisible(part) {
  const group = groupByPartId.get(part.id);
  return visibilityControls.get(`part:${part.id}`) !== false &&
    (!group || cuttingGroupVisibility.get(group.id) !== false);
}

function syncGroupVisibilityButtons() {
  document.querySelectorAll('.group-visibility-toggle').forEach((button, index) => {
    updateGroupVisibilityButton(result.cutting_groups[index], button);
  });
}

function applyPartVisibility() {
  for (const part of result.parts) {
    const root = partRoots.get(part.role);
    const group = groupByPartId.get(part.id);
    const groupVisible = !group || cuttingGroupVisibility.get(group.id) !== false;
    const partVisible = visibilityControls.get(`part:${part.id}`) !== false;
    const visible = partVisible && groupVisible;
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
  const memberRoles = new Set(result.parts
    .filter(part => selectedPartIds.has(part.id))
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
  const model = viewer.model ?? viewer.scene.getObjectByName('base_cabinet');
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
      else if (part) selectTreeParts([part], friendlyPartLabel(part));
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
  for (const group of result.cutting_groups) cuttingGroupVisibility.set(group.id, true);
  syncGroupVisibilityButtons();
  syncVisibilityControls();
  applyPartVisibility();
});
document.getElementById('isolate-selection')?.addEventListener('click', () => {
  if (!selectedPartIds.size) return;
  for (const part of result.parts) visibilityControls.set(`part:${part.id}`, selectedPartIds.has(part.id));
  for (const item of result.cutting_groups) {
    cuttingGroupVisibility.set(item.id, item.members.some(id => selectedPartIds.has(id)));
  }
  syncGroupVisibilityButtons();
  syncVisibilityControls();
  applyPartVisibility();
});
document.getElementById('reset-selection')?.addEventListener('click', () => {
  selectGroup(null);
});
ui.drawerPose?.addEventListener('click', () => {
  if (viewer && (drawerPartNodes.length || legacyDrawerPose)) setDrawerPose(!drawersOpen);
});
ui.doorPose?.addEventListener('click', () => {
  if (viewer && doorPartNodes.length) setDoorPose(!doorsOpen);
});
ui.panelOpacity?.addEventListener('input', () => {
  setPanelOpacity(Number(ui.panelOpacity.value) / 100);
});

start();
