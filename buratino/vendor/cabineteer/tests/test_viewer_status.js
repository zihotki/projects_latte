const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/cabineteer/assets/viewer_controls.js'), 'utf8');
const start = source.indexOf('async function refreshStatus()');
const end = source.indexOf('async function start()', start);
const status = {textContent: '', dataset: {}, hidden: true};
const navigations = [];
const context = {document: {querySelector: () => null}, window: {location: {replace: url => navigations.push(url), search: '?view=iso', hash: '#part'}}, ui: {status}, result: null, fetch: async () => ({ok: true, json: async () => ({status: 'current'})})};
vm.createContext(context);
vm.runInContext(`${source.slice(start, end)}\nthis.refreshStatus = refreshStatus;`, context);

(async () => {
  context.result = {draft_status: 'DRAFT · NOT FOR MANUFACTURING', draft_state: 'draft'};
  await context.refreshStatus();
  assert.equal(status.hidden, true);
  assert.equal(status.textContent, '');

  context.result = {draft_status: 'old status phrase', draft_state: 'stale'};
  await context.refreshStatus();
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Outdated inputs · old draft');

  context.result = null;
  context.window.buratinoPreviewRefresh = true;
  context.fetch = async () => { throw new Error('Server bootstrap owns polling'); };
  await context.refreshStatus();
  assert.equal(status.textContent, 'Outdated inputs · old draft');
  context.window.buratinoPreviewRefresh = false;
  context.fetch = async () => ({ok: true, json: async () => ({status: 'current'})});
  await context.refreshStatus();
  assert.equal(status.hidden, true);
  assert.equal(status.textContent, '');

  context.fetch = async () => ({ok: true, json: async () => ({status: 'stale'})});
  await context.refreshStatus();
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Stale inputs · old draft');

  context.fetch = async () => ({ok: true, json: async () => ({status: 'unavailable', error: 'project.py is missing.'})});
  await context.refreshStatus();
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Inputs unavailable · project.py is missing.');

  context.fetch = async () => { throw new Error('missing status endpoint'); };
  await context.refreshStatus();
  assert.equal(status.hidden, false);
  assert.equal(status.textContent, 'Preview status unavailable');

  context.fetch = async () => ({ok: true, json: async () => ({status: 'updating', revision: 'old'})});
  context.document.querySelector = () => ({content: 'old', dataset: {entry: '/designs/cabinet/preview.html'}});
  await context.refreshStatus();
  assert.equal(status.textContent, 'Updating draft…');
  assert.deepEqual(navigations, []);

  context.fetch = async () => ({ok: true, json: async () => ({status: 'current', revision: 'new'})});
  context.document.querySelector = () => null; // Direct pinned pages stay immutable.
  await context.refreshStatus();
  assert.deepEqual(navigations, []);
  context.document.querySelector = () => ({content: 'old', dataset: {entry: '/designs/cabinet/preview.html'}});
  await context.refreshStatus();
  await context.refreshStatus();
  assert.deepEqual(navigations, ['/designs/cabinet/preview.html?view=iso#part']);
})().catch(error => {
  process.nextTick(() => { throw error; });
});
