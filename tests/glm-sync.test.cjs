const {test}=require('node:test'); const assert=require('node:assert/strict'); const vm=require('node:vm'); const fs=require('node:fs');
test('GLM sync exports only rendered question and final answer, excluding thinking',()=>{
 let listener;const q={id:'row-question-p-0',innerText:'question',compareDocumentPosition:()=>4};const a={id:'row-answer-0',compareDocumentPosition:()=>2,querySelectorAll:()=>[{innerText:'private thinking',closest:()=>({})},{innerText:'final answer',closest:()=>null}]};
 const d={title:'GLM',body:{},querySelector(s){if(s==='#search-input-box textarea')return {value:''};return null;},querySelectorAll(s){if(s==='.answer')return [a];if(s==='[id^="row-question-p-"]')return [q];return [];}};
 const c={document:d,location:{href:'https://chatglm.cn/main/alltoolsdetail?cid=abc'},URL,Node:{DOCUMENT_POSITION_FOLLOWING:4},chrome:{runtime:{onMessage:{addListener(f){listener=f;}}}}};vm.createContext(c);vm.runInContext(fs.readFileSync('extension/glm.js','utf8'),c);let out;listener({type:'bridge_sync'},{},x=>out=x);assert.equal(out.conversation_id,'abc');assert.deepEqual(Array.from(out.messages,m=>[m.role,m.content]),[['user','question'],['assistant','final answer']]);
});
