const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.textContent = '';
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  click() { this.listeners.click?.({currentTarget: this}); }
}

const classNames = new Set();
const body = {classList: {
  add: name => classNames.add(name),
  remove: name => classNames.delete(name),
  contains: name => classNames.has(name),
  toggle(name, force) {
    const enabled = force ?? !classNames.has(name);
    if (enabled) classNames.add(name);
    else classNames.delete(name);
    return enabled;
  },
}};
const elements = new Map();
for (const id of [
  'tree-tab', 'parts-tab', 'settings-tab', 'tree-view', 'parts-view', 'settings-view', 'sheet-title', 'sheet-toggle',
]) elements.set(id, new Element());

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const behavior = source.slice(source.indexOf('function setSheetOpen('), source.indexOf('ui.focusSelection?.addEventListener('));
const context = {
  activeSheetTab: null,
  selectedSheetTab: 'tree-tab',
  document: {body, getElementById: id => elements.get(id)},
};
vm.createContext(context);
vm.runInContext(behavior, context);

const clickTab = id => elements.get(id).click();
const assertTab = (id, selected) => assert.equal(elements.get(id).attributes['aria-selected'], String(selected));
const sheetOpen = () => body.classList.contains('sheet-open');
const sheetToggle = elements.get('sheet-toggle');

clickTab('tree-tab');
assert.equal(sheetOpen(), true, 'clicking an inactive tab opens the sheet');
assertTab('tree-tab', true);
assert.equal(elements.get('tree-view').hidden, false);

clickTab('tree-tab');
assert.equal(sheetOpen(), false, 'clicking the open tab collapses the sheet');
assertTab('tree-tab', false);
assert.equal(sheetToggle.attributes['aria-expanded'], 'false');

sheetToggle.click();
assert.equal(sheetOpen(), true, 'the sheet toggle reopens the last section');
assertTab('tree-tab', true);

clickTab('parts-tab');
assert.equal(sheetOpen(), true, 'switching tabs keeps the sheet open');
assertTab('tree-tab', false);
assertTab('parts-tab', true);
assert.equal(elements.get('parts-view').hidden, false);

clickTab('settings-tab');
assertTab('parts-tab', false);
assertTab('settings-tab', true);
assert.equal(elements.get('settings-view').hidden, false);

sheetToggle.click();
assert.equal(sheetOpen(), false);
assertTab('settings-tab', true, 'the sheet toggle may retain the selected tab');
assert.equal(sheetToggle.attributes['aria-expanded'], 'false');
sheetToggle.click();
assert.equal(sheetOpen(), true);
assertTab('settings-tab', true);
