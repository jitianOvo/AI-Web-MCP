const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function text(value) { return {nodeType:3,textContent:value}; }
function el(tag, attrs={}, ...children) {
  const node={nodeType:1,tagName:tag.toUpperCase(),attrs,childNodes:children.map(x=>typeof x==='string'?text(x):x),
    getAttribute(k){return this.attrs[k]??null;},matches(selector){
      if(selector.includes("aria-label='开始写作'")) return this.tagName==='DIV' && this.attrs.class?.includes('ProseMirror') && ['开始写作','Start writing'].includes(this.attrs['aria-label']);
      if(selector==='article')return this.tagName==='ARTICLE';
      if(selector==='[data-message-author-role]')return 'data-message-author-role' in this.attrs;
      if(selector==='[data-chatgpt-selection-message-id]')return 'data-chatgpt-selection-message-id' in this.attrs;
      if(selector==='[data-message-id]')return 'data-message-id' in this.attrs;
      if(selector.includes('[hidden]'))return 'hidden' in this.attrs || this.attrs['aria-hidden']==='true';
      return false;
    },querySelector(selector){return walk(this).find(n=>n!==this&&n.matches?.(selector))||null;},
    querySelectorAll(){return [];},closest(selector){let n=this;while(n){if(n.matches?.(selector))return n;n=n.parentElement;}return null;},
    contains(other){return walk(this).includes(other);},getClientRects(){return this.attrs.hidden?[]:[{}];},
    compareDocumentPosition(other){return this.order<other.order?4:2;},
    cloneNode(){return el(tag,{...attrs},...this.childNodes.map(n=>n.nodeType===3?n.textContent:n.cloneNode()));}}
  for(const child of node.childNodes)child.parentElement=node;
  Object.defineProperties(node,{children:{get(){return this.childNodes.filter(n=>n.nodeType===1);}},textContent:{get(){return this.childNodes.map(n=>n.textContent).join('');}},innerText:{get(){return this.textContent;}}});
  return node;
}
function walk(node){return [node,...(node.childNodes||[]).flatMap(walk)];}
function load(nodes=[]) {
 let listener;
 const c={console,Map,Set,WeakMap,Date,Promise,MutationObserver:class{observe(){}},setTimeout(){},
  location:{pathname:'/c/fixture-writing',href:'https://chatgpt.com/c/fixture-writing'},
  document:{documentElement:{},querySelector(){return null;},querySelectorAll(selector){
    if(selector.includes("data-message-author-role='user'"))return nodes.filter(n=>n.attrs['data-message-author-role']==='user');
    if(selector.includes("data-message-author-role='assistant'"))return nodes.filter(n=>n.attrs['data-message-author-role']==='assistant');
    if(selector==='[data-chatgpt-selection-message-id]')return nodes.filter(n=>'data-chatgpt-selection-message-id' in n.attrs);
    return [];
  }},chrome:{runtime:{sendMessage:async()=>({}),onMessage:{addListener(f){listener=f;}}}}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('extension/selectors.js','utf8'),c);vm.runInContext(fs.readFileSync('extension/content.js','utf8'),c);
 c.sync=()=>{let result;listener({type:'bridge_sync'},{},r=>result=r);return result;};return c;
}
function editor(...children){return el('div',{class:'ProseMirror','contenteditable':'true','aria-label':'开始写作'},...children);}

test('writing cards retain headings, paragraph breaks, emphasis and lists as Markdown',()=>{
 const body=editor(el('h1',{},'Article title'),el('h2',{},'Subtitle'),el('p',{},'First paragraph.'),el('p',{},'Second ',el('strong',{},'bold'),' line',el('br'), 'continued.'),el('ol',{start:'3'},el('li',{},el('p',{},'Third')),el('li',{},el('p',{},'Fourth'))));
 const c=load();assert.equal(c.writingMarkdown(body),'# Article title\n\n## Subtitle\n\nFirst paragraph.\n\nSecond **bold** line\ncontinued.\n\n3. Third\n4. Fourth');
});
test('only writing editor body is extracted, excluding card controls and composer drafts',()=>{
 const writing=editor(el('h1',{},'Title'),el('p',{},'Body end.'));
 const wrapper=el('div',{},el('button',{},'Copy'),el('span',{},'Writing'),writing,el('div',{'aria-label':'询问 ChatGPT'},'unsent draft'));
 assert.equal(load().cleanText(wrapper),'# Title\n\nBody end.');
});
test('live snapshots follow DOM order and exclude hidden and nested duplicate messages',()=>{
 const u1=el('div',{'data-message-author-role':'user'},'first question');u1.order=1;
 const writing=editor(el('h1',{},'Title'),el('p',{},'Full body.'));
 const a1=el('div',{'data-chatgpt-selection-message-id':'stable-writing'},el('div',{'data-message-author-role':'assistant'},writing));a1.order=2;a1.children[0].order=3;
 const u2=el('div',{'data-message-author-role':'user'},'later question');u2.order=4;
 const a2=el('div',{'data-message-author-role':'assistant','data-message-id':'a2'},'latest ordinary answer');a2.order=5;
 const hidden=el('div',{'data-message-author-role':'user',hidden:true},'old hidden history');hidden.order=0;
 const c=load([u1,a1.children[0],u2,a2,hidden,a1]);const rows=c.sync().messages;
 assert.deepEqual(Array.from(rows,m=>m.role),['user','assistant','user','assistant']);
 assert.equal(rows[1].message_id,'stable-writing');assert.equal(rows[1].content_format,'markdown');assert.equal(rows[1].kind,'writing');
 assert.equal(rows[1].content,'# Title\n\nFull body.');assert.equal(rows[3].content,'latest ordinary answer');
});
