const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {URL};
vm.createContext(context);
const source = 'research/protocol-vision/extension/sanitize.js';
if (fs.existsSync(source)) vm.runInContext(fs.readFileSync(source, 'utf8'), context);

test('capture removes credentials and arbitrary payload values', () => {
  assert.equal(typeof context.ProtocolCapture, 'object');
  const result = context.ProtocolCapture.bodyShape(JSON.stringify({access_token:'secret-token',messages:[{content:{parts:['private prompt']}}],file_id:'file-private'}));
  const encoded = JSON.stringify(result);
  for (const secret of ['secret-token','private prompt','file-private']) assert.ok(!encoded.includes(secret));
  assert.match(encoded, /messages/);
});

test('URLs keep origin and path shape without signed query or conversation ids', () => {
  assert.equal(typeof context.ProtocolCapture, 'object');
  const url = context.ProtocolCapture.urlShape('https://chatgpt.com/backend-api/conversation/12345678-abcd-4321-abcd-123456789012?token=secret');
  assert.ok(!url.includes('secret'));
  assert.ok(!url.includes('12345678-abcd'));
  assert.match(url, /backend-api/);
});

test('SSE only exports event names and JSON structure', () => {
  assert.equal(typeof context.ProtocolCapture, 'object');
  const result = context.ProtocolCapture.bodyShape('event: delta\ndata: {"v":"private answer","p":"/message/content/parts/0"}\n\ndata: [DONE]\n\n');
  assert.ok(!JSON.stringify(result).includes('private answer'));
  assert.equal(result.format, 'sse');
  assert.equal(result.done, true);
});
