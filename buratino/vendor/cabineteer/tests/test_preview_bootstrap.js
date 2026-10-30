const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Execute only the server bootstrap: old captured viewer assets have no refresh code.
const source = fs.readFileSync(path.join(__dirname, '../../../src/buratino/preview.py'), 'utf8');
const script = source.match(/_REFRESH_SCRIPT = r"""\s*<script>([\s\S]*?)<\/script>/)[1];
const timers = [];
const navigations = [];
const banner = {style: {}, dataset: {}, hidden: true};
let ready;
let revision = 'old';
const context = {
  window: {location: {search: '?view=iso', hash: '#part', replace: url => navigations.push(url)}},
  document: {
    querySelector: () => ({content: 'old', dataset: {entry: '/designs/test/preview.html'}}),
    getElementById: () => banner,
    addEventListener: (_event, callback) => { ready = callback; },
  },
  fetch: async () => ({ok: true, json: async () => ({status: 'updating', revision})}),
  setTimeout: callback => timers.push(callback),
};
vm.createContext(context);
vm.runInContext(script, context);
(async () => {
  assert.equal(context.window.buratinoPreviewRefresh, true);
  await ready();
  assert.equal(banner.textContent, 'Updating draft…');
  assert.equal(timers.length, 1);
  revision = 'new';
  await timers.shift()();
  assert.deepEqual(navigations, ['/designs/test/preview.html?view=iso#part']);
  assert.equal(timers.length, 0);
  await ready();
  assert.equal(navigations.length, 1);
})().catch(error => { process.nextTick(() => { throw error; }); });
