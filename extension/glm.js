(() => {
  let active = '', cancelled = '';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const cid = () => new URL(location.href).searchParams.get('cid') || '';
  const input = () => document.querySelector('#search-input-box textarea');
  const scope = () => document.querySelector('.search-box-container');
  const imageState = () => {
    const s=scope(), list=s?.querySelector('.file-list-box-content-list');
    const count=list ? list.children.length : 0;
    const uploading=Boolean(list?.querySelector('[role="progressbar"], [aria-busy="true"], [class*="loading"], [class*="uploading"]'));
    return { image_count:count, uploading, ready:count>0&&!uploading, has_content:Boolean(input()?.value.trim())||count>0 };
  };
  const answers = () => Array.from(document.querySelectorAll('.answer')).map(row => ({row, text:Array.from(row.querySelectorAll('.answer-content-wrap')).filter(n=>!n.closest('.advance-thinking')).map(n=>(n.innerText||'').trim()).filter(Boolean).join('\n')}));
  const questions = () => Array.from(document.querySelectorAll('[id^="row-question-p-"]'));
  const messages = () => {
    const users=questions().map(n=>({node:n,role:'user',content:(n.innerText||'').trim()}));
    const assistant=answers().map(a=>({node:a.row,role:'assistant',content:a.text}));
    return users.concat(assistant).filter(m=>m.content).sort((a,b)=>a.node===b.node?0:(a.node.compareDocumentPosition(b.node)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1)).map(m=>({message_id:`glm-${cid()}-${m.node.id}`,role:m.role,content:m.content,content_hash:`${m.role}:${m.content}`}));
  };
  const isNewChat = () => !cid() && questions().length===0 && answers().length===0 && Boolean(input());
  const generating = () => {
    const icon=document.querySelector('.enter-icon-container .enter_icon');
    const src=icon?.getAttribute('src')||'';
    let stopIcon=false;
    if(src.startsWith('data:image/svg+xml;base64,')) { try { const svg=atob(src.split(',')[1]); stopIcon=/<rect\b[^>]*\bx=["']10["'][^>]*\by=["']10["'][^>]*\bwidth=["']12["'][^>]*\bheight=["']12["']/.test(svg); } catch (_) {} }
    return stopIcon || Boolean(document.querySelector('.enter-icon-container.stop, .enter-icon-container.generating, .stop-generate, [class*="stop-generat"], .advance-thinking:not(:has(.advance-thinking-done))'));
  };
  const error = (code,message) => Object.assign(new Error(message),{code});
  const diagnostics = () => ({file_inputs:Array.from(document.querySelectorAll('input[type=file]')).map(e=>({outerHTML:e.outerHTML,files:Array.from(e.files||[]).map(f=>({name:f.name,type:f.type,size:f.size}))})),file_scope:scope()?.outerHTML.slice(0,30000)||'',upload_alerts:Array.from(document.querySelectorAll('[role=alert],.el-message,[class*=upload-error]')).map(e=>e.innerText),input_values:Array.from(document.querySelectorAll('textarea')).map(el=>({value:el.value,disabled:el.disabled,readOnly:el.readOnly,outerHTML:el.outerHTML})),send_control:document.querySelector('.enter-icon-container')?.outerHTML||'',send_handlers:(()=>{let n=document.querySelector('.enter_icon'),a=[];for(let i=0;n&&i<5;i++,n=n.parentElement)a.push({tag:n.tagName,classes:n.className,events:Object.keys(n._vei||{}),rect:((r)=>({x:r.x,y:r.y,width:r.width,height:r.height}))(n.getBoundingClientRect())});return a;})(),recent_questions:Array.from(document.querySelectorAll('[id^="row-question-p-"]')).slice(-5).map(el=>({id:el.id,text:el.innerText,outerHTML:el.outerHTML.slice(0,3000)})),inputs:Array.from(document.querySelectorAll('textarea, [contenteditable="true"], input[type="file"]')).map(el=>el.outerHTML.slice(0,3000)), buttons:Array.from(document.querySelectorAll('button, [role="button"]')).map(el=>el.outerHTML.slice(0,2000)).slice(-100), body_tail:(document.body?.innerText||'').slice(-10000)});
  const checkCancel = () => { if (cancelled===active && active) throw error('REQUEST_CANCELLED','请求已取消'); };
  async function upload(m) {
    const before=imageState();
    if (!m.skip_paste) {
      if (before.has_content || before.uploading) throw error('COMPOSER_NOT_EMPTY','输入框已有草稿或附件');
      const r=await chrome.runtime.sendMessage({type:'bridge_upload_image',request_id:active,image_path:m.image_path});
      if (!r?.success) throw error(r?.code||'IMAGE_UPLOAD_FAILED',r?.message||'上传失败');
    } else if (!before.image_count) throw error('IMAGE_NOT_ATTACHED','输入框没有已有图片');
    const end=Date.now()+Math.min(120000,Number(m.timeout_ms||600000));
    while(Date.now()<end) { checkCancel(); const state=imageState(); if(state.ready)return state.image_count; await sleep(250); }
    throw error('IMAGE_UPLOAD_TIMEOUT','图片上传未确认');
  }
  function writePrompt(text) {
    const el=input(); if (!el) throw error('INPUT_NOT_FOUND','找不到 GLM 输入框');
    if (el.value.trim()) throw error('COMPOSER_NOT_EMPTY','输入框已有草稿');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,text);
    el.dispatchEvent(new Event('input',{bubbles:true}));
    if(el.value!==text) throw error('INPUT_WRITE_FAILED','输入框写入失败');
  }
  async function task(m) {
    if(active) throw error('EXTENSION_BUSY','目标繁忙'); active=String(m.request_id||'');cancelled='';
    try {
      if(generating()) throw error('PAGE_GENERATING','页面仍在生成');
      const before=answers(), questions=new Set(Array.from(document.querySelectorAll('[id^="row-question-p-"]')));
      const count=m.input_backend==='image'?await upload(m):0;
      if(m.upload_only) return {success:true,result:'',stage:'UPLOADED',uploaded_image_count:count,conversation_id:cid()};
      const prompt=String(m.prompt||'');
      if(prompt) writePrompt(prompt);
      else if(m.input_backend==='image') {
        const candidate=Array.from(document.querySelectorAll('.search-box-container *')).find(n=>n.children.length===0 && n.textContent.trim()==='这是什么');
        if(!candidate) throw error('PROMPT_REQUIRED','没有找到图片候选问题');
        const click=await chrome.runtime.sendMessage({type:"bridge_glm_click_send",request_id:active,action:"default_image"});
        if(!click?.success) throw error(click?.code||"DELIVERY_UNCERTAIN",click?.message||"发送操作未确认，请查询原任务");
      } else throw error('PROMPT_REQUIRED','问题为空');
      if(prompt) {
        const deadline=Date.now()+8000; let button;
        while(Date.now()<deadline) { checkCancel(); button=document.querySelector('.enter-icon-container'); if (button && !button.classList.contains('empty') && button.getAttribute('aria-disabled') !== 'true') break; await sleep(100); }
        if(!button || button.classList.contains('empty') || button.getAttribute('aria-disabled') === 'true') throw error('SEND_BUTTON_UNAVAILABLE','发送按钮未启用；未发送问题');
        const click=await chrome.runtime.sendMessage({type:"bridge_glm_click_send",request_id:active});
        if(!click?.success) throw error(click?.code||"DELIVERY_UNCERTAIN",click?.message||"发送操作未确认，请查询原任务");
      }
      const end=Date.now()+Number(m.timeout_ms||600000);let seen=false,last='',changed=Date.now(),ack=false;
      while(Date.now()<end) {
        checkCancel(); const q=document.querySelectorAll('[id^="row-question-p-"]'); if(Array.from(q).some(n=>!questions.has(n) && (!prompt || (n.innerText||'').includes(prompt)))) ack=true;
        const a=answers(), newest=a[a.length-1];
        if(newest && (a.length>before.length || newest.row!==before[before.length-1]?.row)) {
          seen=true; if(newest.text!==last){last=newest.text;changed=Date.now();}
          if(last && ack && newest.row.querySelector('[id^="interactContainer-"]') && !generating() && Date.now()-changed>=3000) return {success:true,result:last,conversation_id:cid(),message_id:newest.row.id||'',uploaded_image_count:count};
        }
        await sleep(300);
      }
      throw error(ack?'RESPONSE_TIMEOUT':'DELIVERY_UNCERTAIN','未确认完整回答，请查询原任务');
    } finally { active=''; }
  }
  chrome.runtime.onMessage.addListener((m,s,sendResponse)=>{
    const identity={provider:'glm',conversation_id:cid(),url:location.href};
    if(m.type==='bridge_ping'){sendResponse({...identity,ready:!!input()});return false;}
    if(m.type==='bridge_state'){sendResponse({...identity,ready:!!input(),generating:generating(),conversation_title:document.title});return false;}
    if(m.type==='bridge_sync'){sendResponse({...identity,success:true,messages:messages()});return false;}
    if(m.type==='bridge_check_state'||m.type==='bridge_dom_snapshot'){const a=answers();sendResponse({...identity,success:true,page_ready:!!input(),input_ready:!!input(),generating:generating(),user_message_on_screen:questions().some(n=>!String(m.prompt||'').trim()||(n.innerText||'').includes(String(m.prompt).trim())),assistant_present:a.length>0,last_text:a.at(-1)?.text||'',is_new_chat:isNewChat(),input_text:input()?.value||'',matched_user_messages:questions().map(n=>({text:(n.innerText||'').trim(),images:document.querySelectorAll(`[id="${n.id.replace('row-question-p-', 'row-question-img-')}"] img`).length})),dom_detail:diagnostics(),...imageState()});return false;}
    if(m.type==='bridge_check_image_upload'){sendResponse({success:true,...imageState()});return false;}
    if(m.type==='bridge_cancel'){
      const request=String(m.request_id||'');
      if(!active || active!==request){sendResponse({success:false,code:'REQUEST_NOT_ACTIVE'});return false;}
      if(generating()) { chrome.runtime.sendMessage({type:'bridge_glm_click_send',request_id:request,action:'stop'}).then(r=>{cancelled=request;sendResponse(r);}).catch(e=>{cancelled=request;sendResponse({success:false,code:'STOP_FAILED',message:e.message});});return true; }
      cancelled=request;sendResponse({success:true});return false;
    }
    if(m.type==='bridge_new_chat'){
      if(imageState().has_content){sendResponse({success:false,code:'COMPOSER_NOT_EMPTY',message:'输入框已有草稿或附件'});return false;}
      const el=Array.from(document.querySelectorAll('a,button,div,span')).find(n=>n.children.length===0 && n.textContent.trim()==='新对话');
      if(!el){sendResponse({success:false,code:'NEW_CHAT_FAILED',message:'未找到新对话入口'});return false;}
      el.click(); (async()=>{for(let i=0;i<100;i++){if(!cid()&&input())return {success:true,already:false,conversation_id:''};await sleep(200);}throw error('NEW_CHAT_FAILED','未确认进入新对话');})().then(sendResponse).catch(e=>sendResponse({success:false,code:e.code,message:e.message}));return true;
    }
    if(m.type==='bridge_task'){task(m).then(sendResponse).catch(e=>sendResponse({success:false,code:e.code||'GLM_ERROR',message:e.message}));return true;}
    return false;
  });
})();
