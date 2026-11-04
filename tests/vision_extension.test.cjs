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
  if (file === 'content.js') context.chrome.runtime.onMessage.addListener = listener => {context.pageMessageListener = listener;};
  if (file === 'background.js') vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/providers.js'), 'utf8'), context);
  if (file === 'content.js') vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/selectors.js'), 'utf8'), context);
  let source = fs.readFileSync(path.join(__dirname, '../extension', file), 'utf8');
  // Expose content-script closure functions to this isolated test VM.
  if (file === 'content.js') source = source.slice(source.indexOf('let activeRequestId')).replace(/\}\)\(\);\s*$/, '');
  vm.runInContext(source, context);
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

test('rendered inline and fenced code can acknowledge the complete submitted text', async () => {
  const c = load('content.js');
  const prompt = 'Report\n\nBefore `: > trace` resets per_cpu/stats; call ``a`b`` safely.';
  const content = 'Report\nBefore : > trace resets per_cpu/stats; call a`b safely.';
  assert.equal(c.userPromptMatches(content, prompt), true);
  assert.equal(c.userPromptMatches('Report Before : > trace resets per_cpu/stats; call ``a`b`` safely.', prompt), true);
  assert.equal(c.userPromptMatches('Run\n: > trace\necho "done"\nEnd', 'Run\n```sh\n: > trace\necho "done"\n```\nEnd'), true);
  assert.equal(c.userPromptMatches('const x = `literal`;\nDone', '```js\nconst x = `literal`;\n```\nDone'), true);
  assert.equal(c.userPromptMatches('literal tick stays', 'literal `tick stays'), false);
  assert.equal(c.userPromptMatches('literal `tick stays', 'literal `tick stays'), true);
  assert.equal(c.userPromptMatches('Report Before : > other resets per_cpu/stats; call a`b safely.', prompt), false);
  assert.equal(c.userPromptMatches('Report Before', prompt), false);
  c.messageNodes = () => [{}]; c.roleFromNode = () => 'user';
  c.messageFromNode = () => ({ message_id: 'new-code', content });
  assert.equal(await c.waitForUserMessage(prompt, 20, new Set(['older'])), true);
  let now = 0; c.Date = {now: () => now}; c.delay = async () => {now += 200;};
  assert.equal(await c.waitForUserMessage(prompt, 20, new Set(['new-code'])), false);
});

test('timeout state checks use the same rendered-code matching as submission acknowledgement', () => {
  const c = load('content.js'); let state;
  c.messageNodes = () => [{}]; c.roleFromNode = () => 'user';
  c.cleanText = () => 'Check : > trace now';
  c.answerNodes = () => [];
  c.domSnapshot = () => ({}); c.domDetail = () => ({}); c.userAttachmentCount = () => 0;
  c.pageMessageListener({type: 'bridge_check_state', prompt: 'Check `: > trace` now'}, {}, value => {state = value;});
  assert.equal(state.user_message_on_screen, true);
  c.pageMessageListener({type: 'bridge_check_state', prompt: 'Check `: > other` now'}, {}, value => {state = value;});
  assert.equal(state.user_message_on_screen, false);
});

test('task errors before typing are reported immediately and release the active target', async () => {
  const c = load('background.js'); const events = [];
  c.getBoundTab = async () => null;
  c.sendToBridge = (_, message) => events.push(message);
  c.sendStatus = async () => {};
  await c.runTask({request_id: 'missing-tab', target_id: 'tab-1'}, 'tab-1');
  assert.equal(events.length, 1);
  assert.equal(events[0].type, 'error');
  assert.equal(events[0].code, 'CHATGPT_TAB_NOT_FOUND');
  assert.equal(vm.runInContext('activeRequests.size', c), 0);
});

test('page send failure after CDP typing retains its error and diagnostics without waiting for Bridge timeout', async () => {
  const c = load('background.js'); const events = []; let deliveries = 0;
  c.getBoundTab = async () => ({id: 1, url: 'https://chatgpt.com/c/fixture'});
  c.ensurePageScript = async () => ({ready: true});
  c.cdpTypeAndEnter = async () => vm.runInContext('cdpLastLog = {afterInsert: "typed"}', c);
  c.sendTaskToPage = async () => {deliveries++; return {success: false, code: 'SEND_FAILED', message: 'Not acknowledged'};};
  c.sendToBridge = (_, message) => events.push(message);
  c.sendStatus = async () => {};
  await c.runTask({request_id: 'send-failed', target_id: 'tab-1', prompt: 'typed'}, 'tab-1');
  const errors = events.filter(e => e.type === 'error');
  assert.equal(errors.length, 1);
  assert.equal(errors[0].code, 'SEND_FAILED');
  assert.match(errors[0].message, /Not acknowledged.*cdp=.*typed/);
  assert.equal(deliveries, 1);
  assert.equal(vm.runInContext('activeRequests.size', c), 0);
});

test('uncertain task delivery reports the original error once without resending', async () => {
  const c = load('background.js'); const events = []; let deliveries = 0;
  c.getBoundTab = async () => ({id: 1, url: 'https://chatgpt.com/c/fixture'});
  c.ensurePageScript = async () => ({ready: true});
  c.chrome.tabs.sendMessage = async () => {deliveries++; throw new Error('port closed');};
  c.sendToBridge = (_, message) => events.push(message);
  c.sendStatus = async () => {};
  await c.runTask({request_id: 'uncertain', target_id: 'tab-1', input_backend: 'dom'}, 'tab-1');
  assert.equal(events.length, 1);
  assert.equal(events[0].code, 'DELIVERY_UNCERTAIN');
  assert.equal(deliveries, 1);
  assert.equal(vm.runInContext('activeRequests.size', c), 0);
});

test('extension reload restores a stale page script without refreshing the tab', async () => {
  const c = load('background.js'); let injected = false; let injections = 0;
  c.chrome.tabs.get = async () => ({url: 'https://chatgpt.com/c/fixture'});
  c.chrome.tabs.sendMessage = async () => {
    if (!injected) throw new Error('Receiving end does not exist');
    return {ready: true};
  };
  c.chrome.tabs.reload = async () => {throw new Error('must preserve editing state');};
  c.chrome.scripting = {executeScript: async args => {
    if (args.func) {assert.equal(typeof args.func, 'function'); return;}
    injections++; assert.deepEqual(Array.from(args.files), ['selectors.js', 'content.js']); injected = true;
  }};
  assert.deepEqual(await Promise.all([c.pageReady(1), c.pageReady(1)]), [true, true]);
  assert.equal(injections, 1);
  assert.equal(await c.pageReady(1), true);
  assert.equal(injections, 1);
});

test('content script reinjection keeps one listener and observer per loaded version', () => {
  const c = load('background.js'); let listeners = 0, observers = 0;
  c.chrome.runtime.getManifest = () => ({version: 'fixture-version'});
  c.chrome.runtime.onMessage.addListener = () => listeners++;
  c.MutationObserver = class {observe() {observers++;}};
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/selectors.js'), 'utf8'), c);
  const source = fs.readFileSync(path.join(__dirname, '../extension/content.js'), 'utf8');
  vm.runInContext(source, c); vm.runInContext(source, c);
  assert.equal(listeners, 1); assert.equal(observers, 1);
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
