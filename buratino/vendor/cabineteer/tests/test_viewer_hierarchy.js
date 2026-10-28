const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.dataset = {}; this.attributes = {}; this.listeners = {}; }
  replaceChildren() { this.children = []; }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
}
const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const body = source.slice(source.indexOf('function renderVisibilityControls()'), source.indexOf('function makeEyeButton('));
const root = new Element();
const parts = [
  {id: 'shell', cabinet_id: 'host', ancestor_ids: ['host'], label: 'Shell'},
  {id: 'shelf', cabinet_id: 'host', ancestor_ids: ['host', 'module'], label: 'Shelf'},
  {id: 'door', cabinet_id: 'inner', ancestor_ids: ['host', 'module', 'inner'], label: 'Door'},
];
const context = {
  result: {parts, instances: [{id: 'host', name: 'Host'}, {id: 'module', parent_id: 'host'}, {id: 'inner', parent_id: 'module'}]},
  ui: {visibility: root}, visibilityControls: null,
  document: {createElement: () => new Element(), getElementById: () => new Element()},
  humanizeProjectName: value => value, friendlyPartLabel: part => part.label,
  makeEyeButton: () => new Element(), syncVisibilityControls: () => {},
  syncGroupVisibilityButtons: () => {}, applyPartVisibility: () => {},
  selectTreeParts: items => { context.selected = items.map(item => item.id); },
  isPartVisible: part => context.visibilityControls.get(`part:${part.id}`) !== false,
};
vm.createContext(context);
vm.runInContext(body + '\nrenderVisibilityControls();', context);
const hostRow = root.children[0];
const hostChildren = root.children[1];
assert.equal(hostChildren.children[1].children[1].textContent, 'module');
hostRow.children[1].listeners.click();
assert.deepEqual(Array.from(context.selected), ['shell', 'shelf', 'door']);
hostRow.children[2].listeners.click();
assert.deepEqual(parts.map(p => context.visibilityControls.get(`part:${p.id}`)), [false, false, false]);
hostRow.children[2].listeners.click();
assert.deepEqual(parts.map(p => context.visibilityControls.get(`part:${p.id}`)), [true, true, true]);
const moduleRow = hostChildren.children[1];
moduleRow.children[2].listeners.click();
assert.deepEqual(parts.map(p => context.visibilityControls.get(`part:${p.id}`)), [true, false, false]);
