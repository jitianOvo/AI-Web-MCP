const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
test('cancel ignores mismatched request and clicks stop only for active generation',async()=>{
 let listener, clicks=0; const svg='<svg><rect x="10" y="10" width="12" height="12"/></svg>';const icon={getAttribute:()=>`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`};class T{constructor(){this._value=''} get value(){return this._value}set value(v){this._value=v}dispatchEvent(){}}
 const editor=new T();let gen=false;const document={querySelector(s){if(s==='#search-input-box textarea')return editor;if(s==='.enter-icon-container .enter_icon')return gen?icon:null;if(s==='.enter-icon-container')return {classList:{contains:()=>false},getAttribute:()=>null};return null},querySelectorAll:()=>[]};
 const c={document,URL,location:{href:'https://chatglm.cn/main/alltoolsdetail'},HTMLTextAreaElement:T,Event:class{},atob:s=>Buffer.from(s,'base64').toString(),setTimeout:()=>0,chrome:{runtime:{onMessage:{addListener(f){listener=f}},sendMessage:async(m)=>{if(m.action==='stop')clicks++;return {success:true}}}}};vm.createContext(c);vm.runInContext(fs.readFileSync('extension/glm.js','utf8'),c);
 listener({type:'bridge_task',request_id:'active',prompt:'x',timeout_ms:60000},{},()=>{});await new Promise(r=>setImmediate(r));gen=true;
 let wrong;listener({type:'bridge_cancel',request_id:'other'},{},x=>wrong=x);assert.equal(wrong.code,'REQUEST_NOT_ACTIVE');assert.equal(clicks,0);
 const result=await new Promise(r=>listener({type:'bridge_cancel',request_id:'active'},{},r));assert.equal(result.success,true);assert.equal(clicks,1);
});
