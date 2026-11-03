const test = require('node:test');
const assert = require('node:assert/strict');
const p = require('../extension/providers.js');
test('GLM matches conversation identity and ignores time and language', () => {
 const a='https://chatglm.cn/main/alltoolsdetail?t=123&cid=abc123&lang=zh';
 assert.equal(p.detect(a),'glm'); assert.equal(p.conversationId('glm',a),'abc123');
 assert.equal(p.matches('glm',a,'https://chatglm.cn/main/alltoolsdetail?cid=abc123&t=456'),true);
 assert.equal(p.matches('glm',a,'https://chatglm.cn/main/alltoolsdetail?cid=other'),false);
});
test('provider destination rejects wrong hosts, paths and identity ambiguity', () => {
 for(const value of ['https://evil.example/main/alltoolsdetail?cid=abc','https://chatglm.cn/other?cid=abc','https://chatglm.cn/main/alltoolsdetail?cid=one&cid=two','https://chatglm.cn/main/alltoolsdetail?cid=abc#frag']) assert.throws(()=>p.normalize('glm',value));
 assert.equal(p.detect('https://chatgpt.com/'),'chatgpt');
 assert.throws(()=>p.normalize('chatgpt','https://chatglm.cn/main/alltoolsdetail'));
});
