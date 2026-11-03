const GPT_WEB_PROVIDERS = (() => {
  function detect(value) {
    try { const u = new URL(value); if (u.protocol !== 'https:') return ''; if (['chatgpt.com', 'chat.openai.com'].includes(u.hostname)) return 'chatgpt'; if (u.hostname === 'chatglm.cn') return 'glm'; } catch (_) {} return '';
  }
  function normalize(provider, value) {
    const raw = value || (provider === 'glm' ? 'https://chatglm.cn/main/alltoolsdetail' : 'https://chatgpt.com/');
    let u; try { u = new URL(raw); } catch (_) { throw Object.assign(new Error('Invalid URL'), {code:'INVALID_CONVERSATION_URL'}); }
    const fail = () => { throw Object.assign(new Error('Invalid provider conversation URL'), {code:'INVALID_CONVERSATION_URL'}); };
    if (/\s|\\/.test(raw) || u.username || u.password || u.hash || detect(raw) !== provider) fail();
    if (provider === 'glm') {
      if (u.pathname.replace(/\/+$/, '') !== '/main/alltoolsdetail' || [...u.searchParams.keys()].some(k => !['cid','t','lang'].includes(k)) || u.searchParams.getAll('cid').length > 1 || (u.searchParams.has('cid') && !/^[A-Za-z0-9_-]+$/.test(u.searchParams.get('cid')))) fail();
      return u.href;
    }
    if (provider !== 'chatgpt' || u.search || !/^(?:\/(?:g\/[A-Za-z0-9_-]+\/)?c\/[A-Za-z0-9_-]+)?\/?$/.test(u.pathname)) fail();
    return `https://${u.host}${u.pathname.replace(/\/+$/, '') || '/'}`;
  }
  function conversationId(provider, value) { try { const u = new URL(value); return provider === 'glm' ? u.searchParams.get('cid') || '' : u.pathname.match(/\/c\/([A-Za-z0-9_-]+)\/?$/)?.[1] || ''; } catch (_) { return ''; } }
  function matches(provider, candidate, destination) { try { const a=normalize(provider,candidate), b=normalize(provider,destination), id=conversationId(provider,b); return provider === 'glm' ? Boolean(id && conversationId(provider,a)===id) : a===b; } catch (_) { return false; } }
  return {detect, normalize, conversationId, matches};
})();
if (typeof module !== 'undefined') module.exports = GPT_WEB_PROVIDERS;
