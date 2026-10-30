const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Button {
  constructor() { this.attributes = {}; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const update = source.slice(source.indexOf('function updateFocusSelectionButton()'), source.indexOf('function makeEyeButton('));
const action = source.slice(source.indexOf('function focusOrShowAllSelection()'), source.indexOf("document.getElementById('reset-selection')"));
const parts = [{id: 'a'}, {id: 'b'}, {id: 'c'}];
const button = new Button();
const context = {
  result: {parts}, selectedPartIds: new Set(),
  visibilityControls: new Map(parts.map(part => [`part:${part.id}`, true])),
  ui: {focusSelection: button},
  isPartVisible: part => context.visibilityControls.get(`part:${part.id}`) !== false,
  syncGroupVisibilityButtons() {}, syncVisibilityControls() {}, applyPartVisibility() {},
};
vm.createContext(context);
vm.runInContext(`${update}\n${action}`, context);

context.updateFocusSelectionButton();
assert.equal(button.textContent, 'Isolate selection');
assert.equal(button.disabled, true);
assert.equal(button.attributes['aria-pressed'], 'false');

context.selectedPartIds = new Set(['a']);
context.updateFocusSelectionButton();
assert.equal(button.disabled, false);
context.focusOrShowAllSelection();
assert.deepEqual(parts.map(part => context.visibilityControls.get(`part:${part.id}`)), [true, false, false]);
assert.equal(button.textContent, 'Show all');
assert.equal(button.disabled, false);
assert.equal(button.attributes['aria-pressed'], 'true');

context.selectedPartIds = new Set(['b']);
context.updateFocusSelectionButton();
assert.equal(button.textContent, 'Show all');
context.focusOrShowAllSelection();
assert.deepEqual(parts.map(part => context.visibilityControls.get(`part:${part.id}`)), [true, true, true]);
assert.equal(button.textContent, 'Isolate selection');

context.visibilityControls.set('part:c', false);
context.selectedPartIds = new Set(['a', 'b']);
context.updateFocusSelectionButton();
assert.equal(button.textContent, 'Show all');
context.focusOrShowAllSelection();
assert.deepEqual(parts.map(part => context.visibilityControls.get(`part:${part.id}`)), [true, true, true]);

context.selectedPartIds = new Set(parts.map(part => part.id));
context.updateFocusSelectionButton();
assert.equal(button.disabled, true);
