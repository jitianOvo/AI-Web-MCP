const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load(file, overrides = {}) {
  const context = { setTimeout: (fn, ms) => ms <= 200 ? setTimeout(fn, ms) : 0, clearTimeout, setInterval: () => 0, clearInterval() {},
    console, Map, Set, WeakMap, Date, Promise, URL, navigator: { userAgent: '' },
    importScripts() {}, WebSocket: { OPEN: 1, CONNECTING: 0 },
    MutationObserver: class { observe() {} }, location: { pathname: '/', href: 'https://chatgpt.com/' },
    document: { querySelector: () => null, querySelectorAll: () => [], body: {} },
    chrome: { storage: { local: { get: () => new Promise(() => {} ) } },
      runtime: { onMessage: { addListener() {} }, onInstalled: { addListener() {} }, onStartup: { addListener() {} } },
      tabs: { onUpdated: { addListener() {} }, onRemoved: { addListener() {} }, onCreated: { addListener() {} } },
      alarms: { onAlarm: { addListener() {} } } }, ...overrides };
  vm.createContext(context);
  if (file === 'background.js') vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/providers.js'), 'utf8'), context);
  if (file === 'content.js') vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/selectors.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension', file), 'utf8'), context);
  return context;
}

test('one task delivery when response port closes', async () => {
  let calls = 0;
  const c = load('background.js');
  c.chrome.tabs.sendMessage = async () => { calls++; throw new Error('port closed'); };
  await assert.rejects(c.sendTaskToPage(1, { type: 'bridge_task' }), e => e.code === 'DELIVERY_UNCERTAIN');
  assert.equal(calls, 1);
});

test('file upload uses one DOM.setFileInputFiles call and always detaches', async () => {
  const c = load('background.js');
  const calls = [];
  c.debuggerAttach = async () => calls.push('attach');
  c.debuggerDetach = async () => calls.push('detach');
  c.cdpCommand = async (_, method, params) => {
    calls.push(method);
    if (method === 'Runtime.evaluate') return { result: { objectId: 'file-input' } };
    assert.deepEqual(Array.from(params.files), ['C:\\test.png']);
  };
  await c.uploadImageFile(1, 'C:\\test.png');
  assert.deepEqual(calls, ['attach', 'Runtime.evaluate', 'DOM.setFileInputFiles', 'detach']);
});

test('text-only composer is never an uploaded image', () => {
  const c = load('content.js');
  c.firstMatch = () => ({ closest: () => ({ querySelectorAll: () => [], querySelector: () => null }) });
  c.inputValue = () => 'describe';
  assert.equal(c.composerImageState().ready, false);
});

test('attachment sibling of editor is recognized; upload spinner blocks readiness', () => {
  const c = load('content.js');
  let uploading = false;
  const scope = { querySelectorAll: () => [{ closest: () => null, className: 'attachment' }], querySelector: () => uploading ? {} : null };
  c.firstMatch = () => ({ closest: () => scope });
  c.inputValue = () => '';
  assert.equal(c.composerImageState().ready, true);
  uploading = true;
  assert.equal(c.composerImageState().ready, false);
});

test('historical identical question cannot acknowledge new submission', async () => {
  const c = load('content.js');
  c.messageNodes = () => [{}]; c.roleFromNode = () => 'user';
  c.messageFromNode = () => ({ message_id: 'old', content: 'describe' });
  assert.equal(await c.waitForUserMessage('describe', 1, new Set(['old'])), false);
  c.messageFromNode = () => ({ message_id: 'new', content: 'describe' });
  assert.equal(await c.waitForUserMessage('describe', 10, new Set(['old'])), true);
});

test('clicking send prefers enabled real button without synthetic Enter', () => {
  const c = load('content.js');
  let clicks = 0;
  c.firstMatch = selectors => selectors === c.GPT_WEB_SELECTORS.input ? {} : { click: () => clicks++, getAttribute: () => null };
  c.pressEnterToSend = () => { throw new Error('must not synthesize Enter'); };
  assert.equal(c.clickSendWithFallback(), true);
  assert.equal(clicks, 1);
});

test('new answer resolves even when total message count stays constant', async () => {
  const c = load('content.js');
  let now = 0;
  c.Date = { now: () => now };
  c.delay = async () => { now += 700; };
  c.answerNodes = () => [{}];
  c.messageFromNode = () => ({ message_id: 'new-answer', content: 'PIC-8842' });
  c.cleanText = () => 'PIC-8842';
  c.firstMatch = () => null;
  c.progress = () => {};
  assert.equal(await c.waitForAnswer('r', new Set(['old-answer']), 3000), 'PIC-8842');
});

test('history URL rejects foreign origins, credentials and non-chat paths', () => {
  const c = load('background.js');
  assert.equal(c.normalizeChatGPTDestination('https://chatgpt.com/g/g-project/c/old-123/'), 'https://chatgpt.com/g/g-project/c/old-123');
  for (const url of ['https://evil.example/c/id', 'https://user@chatgpt.com/c/id', 'http://chatgpt.com/c/id', 'https://chatgpt.com/c/id?q=x', 'https://chatgpt.com/c/id#x', 'https://chatgpt.com/c/id/more']) {
    assert.throws(() => c.normalizeChatGPTDestination(url), e => e.code === 'INVALID_CHATGPT_URL');
  }
});

test('opening old URL reuses matching tab and returns exact conversation identity', async () => {
  const c = load('background.js');
  const url = 'https://chatgpt.com/c/old-123';
  const tab = {id: 7, windowId: 3, url, status: 'complete'};
  let creates = 0, reply;
  c.chrome.tabs.query = async () => [{id: 8, url: 'https://chatgpt.com/c/other'}, tab];
  c.chrome.tabs.get = async () => tab;
  c.chrome.tabs.create = async () => {creates++;};
  c.chrome.tabs.update = async () => {};
  c.chrome.windows = {update: async () => {}};
  c.pageReady = async () => true;
  c.bindSpecificTab = async id => {assert.equal(id, 7); return {target_id: 'tab-7'};};
  c.sendToBridge = (target, message) => {reply = message;};
  await c.openTabFromBridge({url, request_id: 'open-old'}, 'unbound');
  assert.equal(creates, 0);
  assert.equal(reply.reused, true);
  assert.equal(reply.conversation_id, 'old-123');
  assert.equal(reply.url, url);
  assert.equal(reply.target_id, 'tab-7');
});

test('history URL opening creates missing chat at given URL and fails on redirect', async () => {
  const c = load('background.js');
  const url = 'https://chatgpt.com/c/old-123';
  const tab = {id: 7, windowId: 3, url, status: 'complete'};
  let reply, bindings = 0;
  c.chrome.tabs.query = async () => [];
  c.chrome.tabs.get = async () => ({...tab, url: 'https://chatgpt.com/'});
  c.chrome.tabs.create = async options => {assert.equal(options.url, url); return tab;};
  c.chrome.tabs.update = async () => {};
  c.chrome.windows = {update: async () => {}};
  c.pageReady = async () => true;
  c.bindSpecificTab = async () => {bindings++;};
  c.sendToBridge = (target, message) => {reply = message;};
  await c.openTabFromBridge({url, request_id: 'open-old'}, 'unbound');
  assert.equal(reply.code, 'CONVERSATION_URL_MISMATCH');
  assert.equal(bindings, 0);
});


test('history selection skips stale content scripts without reloading existing drafts', async () => {
  const c = load('background.js');
  const url = 'https://chatgpt.com/c/old-123';
  const stale = {id: 7, windowId: 3, url, status: 'complete'};
  const ready = {...stale, id: 8};
  c.chrome.tabs.query = async () => [stale, ready];
  c.chrome.tabs.get = async () => ready;
  c.chrome.tabs.create = async () => {throw new Error('must reuse ready history tab');};
  c.chrome.tabs.reload = async () => {throw new Error('must preserve existing drafts');};
  c.chrome.tabs.update = async () => {};
  c.chrome.windows = {update: async () => {}};
  c.pageReady = async id => id === 8;
  c.bindSpecificTab = async id => ({target_id: `tab-${id}`});
  let reply;
  c.sendToBridge = (target, message) => {reply = message;};
  await c.openTabFromBridge({url, request_id: 'open-old'}, 'unbound');
  assert.equal(reply.tab_id, 8);
  assert.equal(reply.reused, true);
});
