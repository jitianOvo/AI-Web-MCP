const {test}=require('node:test'); const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
test('observed stop-square icon means generating even without thinking node',()=>{
 let listener;const svg='<svg><rect width="32" height="32"/><rect x="10" y="10" width="12" height="12" rx="2" fill="white"/></svg>'; const icon={getAttribute:()=>`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`}; const document={title:'GLM',querySelector:s=>s==='.enter-icon-container .enter_icon'?icon:s==='#search-input-box textarea'?{}:null,querySelectorAll:()=>[]};
 const c={document,location:{href:'https://chatglm.cn/main/alltoolsdetail'},URL,atob:s=>Buffer.from(s,'base64').toString(),chrome:{runtime:{onMessage:{addListener(f){listener=f;}}}}};vm.createContext(c);vm.runInContext(fs.readFileSync('extension/glm.js','utf8'),c);let result;listener({type:'bridge_state'},{},r=>result=r);assert.equal(result.generating,true);
});
