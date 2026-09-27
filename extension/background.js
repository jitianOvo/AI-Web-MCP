importScripts("config.js");

const CONTROL_TARGET_ID = "unbound";
let sockets = new Map();
let reconnectTimers = new Map();
let boundTabs = {};
let activeRequests = new Map();
let heartbeatTimer = null;
let pendingEventWrite = Promise.resolve();
const MAX_PENDING_EVENTS = 500;

chrome.storage.local.get(["boundTabs", "boundTabId"]).then((saved) => {
  boundTabs = saved.boundTabs && typeof saved.boundTabs === "object" ? saved.boundTabs : {};
  if (Number.isInteger(saved.boundTabId) && !Object.values(boundTabs).includes(saved.boundTabId)) {
    boundTabs["bound-tab"] = saved.boundTabId;
  }
  ensureReconnectAlarm();
  connectBridge(CONTROL_TARGET_ID);
  for (const targetId of Object.keys(boundTabs)) connectBridge(targetId);
  autoBindSingleTab();
});

function ensureReconnectAlarm() {
  chrome.alarms.create("bridge-reconnect", { delayInMinutes: 0.05, periodInMinutes: 0.5 });
}

function isChatGPTUrl(url) {
  return Boolean(url && (url.startsWith("https://chatgpt.com/") || url.startsWith("https://chat.openai.com/")));
}

function browserInfo() {
  const userAgent = navigator.userAgent || "";
  const edge = userAgent.match(/Edg\/([\d.]+)/i);
  const chrome = userAgent.match(/Chrome\/([\d.]+)/i);
  if (edge) return { name: "edge", version: edge[1] };
  if (chrome) return { name: "chrome", version: chrome[1] };
  return { name: "chromium", version: "" };
}

async function chatgptTabs() {
  const tabs = await chrome.tabs.query({ url: ["https://chatgpt.com/*", "https://chat.openai.com/*"] });
  return tabs.map((tab) => ({
    tab_id: tab.id,
    tab_title: tab.title || "",
    tab_url: tab.url || "",
    active: Boolean(tab.active),
    window_id: tab.windowId,
  }));
}

async function pruneDeadBoundTabs() {
  let changed = false;
  for (const targetId of Object.keys(boundTabs)) {
    try {
      const tab = await chrome.tabs.get(Number(boundTabs[targetId]));
      if (!tab || !isChatGPTUrl(tab.url)) throw new Error("not chatgpt");
    } catch (_) {
      delete boundTabs[targetId];
      changed = true;
      const socket = sockets.get(targetId);
      if (socket) socket.close();
    }
  }
  if (changed) await chrome.storage.local.set({ boundTabs });
}

async function autoBindSingleTab() {
  try {
    await pruneDeadBoundTabs();
    if (Object.keys(boundTabs).length > 0) return;
    const tabs = await chatgptTabs();
    if (tabs.length !== 1) return;
    const tab = tabs[0];
    const targetId = `tab-${tab.tab_id}`;
    boundTabs[targetId] = tab.tab_id;
    await chrome.storage.local.set({ boundTabs, boundTabId: tab.tab_id });
    connectBridge(targetId);
    setTimeout(() => sendStatus(targetId), 300);
  } catch (_) {}
}

async function bindSpecificTab(tabId) {
  const tab = await chrome.tabs.get(Number(tabId));
  if (!tab || !isChatGPTUrl(tab.url)) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "指定标签页不是 ChatGPT 网页");
  for (const [targetId, boundTabId] of Object.entries(boundTabs)) {
    if (Number(boundTabId) === Number(tab.id)) return { target_id: targetId, title: tab.title || "ChatGPT" };
  }
  const targetId = `tab-${tab.id}`;
  boundTabs[targetId] = tab.id;
  await chrome.storage.local.set({ boundTabs, boundTabId: tab.id });
  connectBridge(targetId);
  setTimeout(() => sendStatus(targetId), 300);
  return { target_id: targetId, title: tab.title || "ChatGPT" };
}

async function bindTabFromBridge(message, socketTargetId) {
  const replyTarget = socketTargetId || CONTROL_TARGET_ID;
  try {
    const result = await bindSpecificTab(message.tab_id);
    sendToBridge(replyTarget, {
      type: "bound_result",
      request_id: String(message.request_id || ""),
      target_id: result.target_id,
      title: result.title,
      success: true,
    });
  } catch (error) {
    sendToBridge(replyTarget, {
      type: "error",
      request_id: String(message.request_id || ""),
      code: error.code || "BIND_FAILED",
      message: error.detail || error.message || String(error),
    });
  }
}

async function focusEditorFromBridge(message, targetId) {
  await activateBoundTab(targetId);
}

// Vision path: the local bridge has already placed an image on the system
// clipboard.  Focus the composer, paste with a real Ctrl+V, wait for the page
// upload to finish, then send prompt + text through the normal CDP pipeline.
async function sendImageFromBridge(message, targetId) {
  const requestId = String(message.request_id || "");
  try {
    const tab = await getBoundTab(targetId);
    if (!tab) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "请先绑定 ChatGPT 标签页");
    sendToBridge(targetId, { type: "progress", request_id: requestId, stage: "VISION_PASTE", detail: "pasting image" });
    await ensureWindowForeground(tab.id);
    await debuggerAttach(tab.id);
    try {
      await cdpFocusEditor(tab.id);  // select-all clears composer; fine before paste
      // Ctrl+V dispatches a trusted paste with the system clipboard image.
      // Full Ctrl+V key sequence (rawKeyDown + char + keyUp) so the renderer
      // performs a real paste from the system clipboard.
      await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "rawKeyDown", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
      await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "char", key: "v", text: "v", unmodifiedText: "v", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
      await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "keyUp", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
      await new Promise((resolve) => setTimeout(resolve, 300));
    } finally {
      await debuggerDetach(tab.id);
    }
    // When the bridge already pasted the image at the OS level (--paste), skip
    // the CDP Ctrl+V and go straight to waiting for the upload.
    if (message.pasted !== true) {
      await ensureWindowForeground(tab.id);
      await debuggerAttach(tab.id);
      try {
        await cdpFocusEditor(tab.id);  // select-all clears composer; fine before paste
        // Full Ctrl+V key sequence (rawKeyDown + char + keyUp) so the renderer
        // performs a real paste from the system clipboard.
        await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "rawKeyDown", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
        await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "char", key: "v", text: "v", unmodifiedText: "v", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
        await cdpCommand(tab.id, "Input.dispatchKeyEvent", { type: "keyUp", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
        await new Promise((resolve) => setTimeout(resolve, 300));
      } finally {
        await debuggerDetach(tab.id);
      }
    }
    // Wait until the composer shows the uploaded image and upload finished.
    sendToBridge(targetId, { type: "progress", request_id: requestId, stage: "VISION_UPLOAD", detail: "waiting upload" });
    const uploadDeadline = Date.now() + 180000;
    let ready = false;
    while (Date.now() < uploadDeadline) {
      const state = await sendTaskToPage(tab.id, { type: "bridge_check_image_upload" }, 5000);
      if (state && state.ready) { ready = true; break; }
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    if (!ready) {
      // ChatGPT keeps the send queued until the upload finishes, so do not
      // block the pipeline on slow networks: proceed and let the page send.
      sendToBridge(targetId, { type: "progress", request_id: requestId, stage: "VISION_UPLOAD_SLOW", detail: "upload not confirmed; relying on page auto-send" });
    }
    sendToBridge(targetId, { type: "progress", request_id: requestId, stage: "VISION_UPLOADED", detail: "upload ready" });
    // Now send prompt + text through the standard pipeline.
    // Append prompt text after the pasted image (do NOT select-all; that would
    // delete the image).  Then Enter submits the image+text message.
    const prompt = String(message.prompt || "请描述这张图片");
    await debuggerAttach(tab.id);
    try {
      await cdpFocusComposerEnd(tab.id);  // caret to end, keep the pasted image
      await cdpCommand(tab.id, "Input.insertText", { text: prompt });
      await new Promise((resolve) => setTimeout(resolve, 400));
    } finally {
      await debuggerDetach(tab.id);
    }
    // Wait for user message + answer through the normal content pipeline.
    const response = await sendTaskToPage(tab.id, {
      type: "bridge_task",
      request_id: requestId,
      conversation_id: String(message.conversation_id || "current"),
      prompt,
      expected_format: String(message.expected_format || "text"),
      timeout_ms: Number(message.timeout_ms || 600000),
      input_backend: "send_only",  // text+image already in composer; only click send + read
    });
    if (!response?.success) throw bridgeError(response?.code || "VISION_SEND_FAILED", response?.message || "图片消息发送失败");
    sendToBridge(targetId, { type: "result", request_id: requestId, target_id: targetId, result: response.result, conversation_id: response.conversation_id, message_id: response.message_id });
  } catch (error) {
    sendToBridge(targetId, {
      type: "error", request_id: requestId, target_id: targetId,
      code: error.code || "VISION_SEND_FAILED", message: error.detail || error.message || String(error),
    });
  } finally {
    await sendStatus(targetId);
  }
}

async function activateBoundTab(targetId) {
  const tab = await getBoundTab(targetId);
  if (!tab) return null;
  try {
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    await sendTaskToPage(tab.id, { type: "bridge_focus_editor" });
  } catch (_) {}
  return tab;
}

async function reloadExtensionFromBridge(message, socketTargetId) {
  const replyTarget = socketTargetId || CONTROL_TARGET_ID;
  sendToBridge(replyTarget, { type: "reload_result", request_id: String(message.request_id || ""), success: true });
  const tabId = Number(message.tab_id || 0);
  if (tabId) { try { await chrome.tabs.reload(tabId); } catch (_) {} }
  try { chrome.runtime.reload(); } catch (_) {}
}

async function openTabFromBridge(message, socketTargetId) {
  const replyTarget = socketTargetId || CONTROL_TARGET_ID;
  try {
    // Some installs run with no visible window (--no-startup-window), where
    // chrome.tabs.create fails with "No current window". Create a window first.
    let tab;
    try {
      tab = await chrome.tabs.create({ url: "https://chatgpt.com/" });
    } catch (noWindow) {
      const win = await chrome.windows.create({ url: "https://chatgpt.com/", focused: true });
      tab = win && win.tabs ? win.tabs[0] : null;
      if (!tab) throw noWindow;
    }
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      const current = await chrome.tabs.get(tab.id);
      if (current?.status === "complete") break;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    const readyDeadline = Date.now() + 30000;
    while (Date.now() < readyDeadline) {
      if (await pageReady(tab.id)) break;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    const ready = await pageReady(tab.id);
    const bound = await bindSpecificTab(tab.id);
    sendToBridge(replyTarget, {
      type: "open_result", request_id: String(message.request_id || ""),
      tab_id: tab.id, target_id: bound.target_id, ready: Boolean(ready), success: true,
    });
  } catch (error) {
    sendToBridge(replyTarget, {
      type: "error", request_id: String(message.request_id || ""),
      code: error.code || "OPEN_TAB_FAILED", message: error.detail || error.message || String(error),
    });
  }
}

async function newChatFromBridge(message, targetId) {
  try {
    const tab = await getBoundTab(targetId);
    if (!tab) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "请先绑定 ChatGPT 标签页");
    const response = await sendTaskToPage(tab.id, { type: "bridge_new_chat" });
    sendToBridge(targetId, {
      type: "new_chat_result", request_id: String(message.request_id || ""), target_id: targetId,
      conversation_id: response?.conversation_id || "", is_new_chat: Boolean(response?.success && response?.already), success: true,
    });
  } catch (error) {
    sendToBridge(targetId, {
      type: "error", request_id: String(message.request_id || ""), target_id: targetId,
      code: error.code || "NEW_CHAT_FAILED", message: error.detail || error.message || String(error),
    });
  }
}

async function checkStateFromBridge(message, targetId) {
  try {
    const tab = await getBoundTab(targetId);
    if (!tab) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "请先绑定 ChatGPT 标签页");
    const response = await sendTaskToPage(tab.id, { type: "bridge_check_state", prompt: String(message.prompt || "") });
    sendToBridge(targetId, {
      type: "state_result", request_id: String(message.request_id || ""), target_id: targetId, state: response || {}, success: true,
    });
  } catch (error) {
    sendToBridge(targetId, {
      type: "error", request_id: String(message.request_id || ""), target_id: targetId,
      code: error.code || "STATE_FAILED", message: error.detail || error.message || String(error),
    });
  }
}

function targetIdForTab(tabId) {
  for (const [targetId, boundTabId] of Object.entries(boundTabs)) {
    if (Number(boundTabId) === Number(tabId)) return targetId;
  }
  return "";
}

function isSocketOpen(targetId) {
  return sockets.get(targetId)?.readyState === WebSocket.OPEN;
}

function anySocketOpen() {
  return Array.from(sockets.values()).some((socket) => socket.readyState === WebSocket.OPEN);
}

function connectBridge(targetId) {
  const existing = sockets.get(targetId);
  if (existing && [WebSocket.OPEN, WebSocket.CONNECTING].includes(existing.readyState)) return;
  clearTimeout(reconnectTimers.get(targetId));
  const socket = new WebSocket(`${GPT_WEB_MCP_CONFIG.websocketUrl}?token=${encodeURIComponent(GPT_WEB_MCP_CONFIG.bridgeToken)}`);
  sockets.set(targetId, socket);
  socket.onopen = async () => {
    await sendStatus(targetId, "hello");
    await replayPendingEvents(targetId);
  };
  socket.onclose = () => {
    if (sockets.get(targetId) === socket) sockets.delete(targetId);
    reconnectTimers.set(targetId, setTimeout(() => connectBridge(targetId), GPT_WEB_MCP_CONFIG.reconnectDelayMs));
  };
  socket.onerror = () => {};
  socket.onmessage = async (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (message.type === "task") await runTask(message, targetId);
    if (message.type === "cancel") await cancelTask(message.request_id, targetId);
    if (message.type === "sync") await syncPage(message, targetId);
    if (message.type === "bind_tab") await bindTabFromBridge(message, targetId);
    if (message.type === "open_tab") await openTabFromBridge(message, targetId);
    if (message.type === "new_chat") await newChatFromBridge(message, targetId);
    if (message.type === "check_state") await checkStateFromBridge(message, targetId);
    if (message.type === "reload_extension") await reloadExtensionFromBridge(message, targetId);
    if (message.type === "focus") await focusEditorFromBridge(message, targetId);
    if (message.type === "send_image") await sendImageFromBridge(message, targetId);
  };
}

function sendToBridge(targetId, payload) {
  const socket = sockets.get(targetId);
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
    return;
  }
  if (payload.type === "message_event") queuePendingEvent(targetId, payload);
}

function queuePendingEvent(targetId, payload) {
  pendingEventWrite = pendingEventWrite.then(async () => {
    const saved = await chrome.storage.local.get(["pendingBridgeEvents"]);
    const pending = saved.pendingBridgeEvents && typeof saved.pendingBridgeEvents === "object" ? saved.pendingBridgeEvents : {};
    const events = Array.isArray(pending[targetId]) ? pending[targetId] : [];
    events.push(payload);
    pending[targetId] = events.slice(-MAX_PENDING_EVENTS);
    await chrome.storage.local.set({ pendingBridgeEvents: pending });
  }).catch(() => {});
}

async function replayPendingEvents(targetId) {
  const socket = sockets.get(targetId);
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  await pendingEventWrite;
  const saved = await chrome.storage.local.get(["pendingBridgeEvents"]);
  const pending = saved.pendingBridgeEvents && typeof saved.pendingBridgeEvents === "object" ? saved.pendingBridgeEvents : {};
  const events = Array.isArray(pending[targetId]) ? pending[targetId] : [];
  if (!events.length) return;
  for (const event of events) {
    if (socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(event));
  }
  delete pending[targetId];
  await chrome.storage.local.set({ pendingBridgeEvents: pending });
}

function startHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(() => {
    for (const targetId of sockets.keys()) sendToBridge(targetId, { type: "heartbeat", timestamp: Date.now(), target_id: targetId });
  }, 20000);
}

startHeartbeat();

async function getBoundTab(targetId) {
  if (!targetId || targetId === CONTROL_TARGET_ID) return null;
  const tabId = Number(boundTabs[targetId]);
  if (!Number.isInteger(tabId)) return null;
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!isChatGPTUrl(tab.url)) return null;
    return tab;
  } catch (_) {
    return null;
  }
}

async function pageReady(tabId) {
  try { return Boolean((await chrome.tabs.sendMessage(tabId, { type: "bridge_ping" }))?.ready); }
  catch (_) { return false; }
}

async function pageState(tabId) {
  try {
    const state = await chrome.tabs.sendMessage(tabId, { type: "bridge_state" });
    return {
      ready: Boolean(state?.ready),
      generating: Boolean(state?.generating),
      conversation_title: String(state?.conversation_title || ""),
      url: String(state?.url || ""),
    };
  } catch (_) {
    return { ready: false, generating: false, conversation_title: "", url: "" };
  }
}

async function sendStatus(targetId, type = "status") {
  if (!isSocketOpen(targetId)) return;
  const tab = await getBoundTab(targetId);
  const browser = browserInfo();
  const page = tab ? await pageState(tab.id) : { ready: false, generating: false, conversation_title: "" };
  const tabs = await chatgptTabs();
  sendToBridge(targetId, {
    type,
    tab_bound: Boolean(tab),
    page_ready: tab ? page.ready : false,
    generating: tab ? page.generating : false,
    conversation_title: tab ? page.conversation_title : "",
    tab_id: tab?.id || null,
    tab_title: tab?.title || "",
    tab_url: tab?.url || "",
    target_id: targetId,
    browser: browser.name,
    browser_version: browser.version,
    extension_version: chrome.runtime.getManifest().version,
    tabs,
  });
}

async function runTask(message, socketTargetId) {
  const targetId = String(message.target_id || socketTargetId);
  if (activeRequests.has(targetId)) {
    sendToBridge(targetId, { type: "error", request_id: message.request_id, target_id: targetId, code: "EXTENSION_BUSY", message: "当前目标标签页仍在处理上一项任务" });
    return;
  }
  activeRequests.set(targetId, String(message.request_id || ""));
  try {
    const tab = await getBoundTab(targetId);
    if (!tab) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "请先绑定 ChatGPT 标签页");
    const backend = String(message.input_backend || "cdp");
    let inputDiag = "";
    let inputBackend = backend;
    if (backend === "cdp") {
      try {
        await cdpTypeAndEnter(tab.id, String(message.prompt || ""));
        sendToBridge(targetId, { type: "progress", request_id: message.request_id, stage: "INPUT_SENT", detail: JSON.stringify(cdpLastLog || {}) });
        inputDiag = JSON.stringify(cdpLastLog || {});
        inputBackend = "send_only";  // click send in page (robust chain)
      } catch (error) {
        inputBackend = "dom";
        sendToBridge(targetId, { type: "progress", request_id: message.request_id, stage: "FALLBACK_DOM", detail: error.code || "CDP_FAILED" });
      }
    }
    const response = await sendTaskToPage(tab.id, {
      type: "bridge_task",
      request_id: String(message.request_id || ""),
      conversation_id: String(message.conversation_id || "current"),
      prompt: String(message.prompt || ""),
      expected_format: String(message.expected_format || "text"),
      timeout_ms: Number(message.timeout_ms || 600000),
      input_backend: inputBackend,
    });
    if (!response?.success) throw bridgeError(response?.code || "EXTENSION_ERROR", response?.message || "页面没有返回结果");
    sendToBridge(targetId, { type: "result", request_id: message.request_id, target_id: targetId, result: response.result, conversation_id: response.conversation_id, message_id: response.message_id });
  } catch (error) {
    const detail = (error.detail || error.message || String(error)) + (inputDiag ? " | cdp=" + inputDiag : "");
    sendToBridge(targetId, { type: "error", request_id: message.request_id, target_id: targetId, code: error.code || "EXTENSION_ERROR", message: detail });
  } finally {
    activeRequests.delete(targetId);
    await sendStatus(targetId);
  }
}

async function sendTaskToPage(tabId, payload, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try { return await chrome.tabs.sendMessage(tabId, payload); }
    catch (error) { lastError = error; await new Promise((resolve) => setTimeout(resolve, 300)); }
  }
  throw bridgeError("CHATGPT_PAGE_NOT_READY", lastError?.message || "内容脚本尚未就绪");
}

async function cancelTask(requestId, targetId) {
  const tab = await getBoundTab(targetId);
  if (tab) {
    try { await chrome.tabs.sendMessage(tab.id, { type: "bridge_cancel", request_id: requestId }); } catch (_) {}
  }
}

async function syncPage(message, targetId) {
  try {
    const tab = await getBoundTab(targetId);
    if (!tab) throw bridgeError("CHATGPT_TAB_NOT_FOUND", "请先绑定 ChatGPT 标签页");
    const response = await sendTaskToPage(tab.id, { type: "bridge_sync", conversation_id: String(message.conversation_id || "current") });
    if (!response?.success) throw bridgeError(response?.code || "SYNC_FAILED", response?.message || "页面同步失败");
    sendToBridge(targetId, { type: "sync_result", request_id: String(message.request_id || ""), target_id: targetId, conversation_id: response.conversation_id, messages: response.messages || [] });
  } catch (error) {
    sendToBridge(targetId, { type: "error", request_id: String(message.request_id || ""), target_id: targetId, code: error.code || "SYNC_FAILED", message: error.detail || error.message || String(error) });
  }
}

function bridgeError(code, detail) {
  const error = new Error(code);
  error.code = code;
  error.detail = detail;
  return error;
}

function debuggerAttach(tabId) {
  return new Promise((resolve, reject) => {
    chrome.debugger.attach({ tabId }, "1.3", () => {
      const err = chrome.runtime.lastError;
      if (err) reject(bridgeError("DEBUGGER_BUSY", String(err.message))); else resolve();
    });
  });
}

function debuggerDetach(tabId) {
  return new Promise((resolve) => chrome.debugger.detach({ tabId }, () => resolve()));
}

// CDP synthetic key events are dropped while the browser window is backgrounded.
// Bring the target tab's window to the foreground and activate the tab first.
async function ensureWindowForeground(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab && tab.windowId != null) {
      // chrome.windows.update({focused:true}) does NOT un-minimize a window,
      // so first restore state then focus the window and activate the tab.
      try {
        const win = await chrome.windows.get(tab.windowId);
        if (win && win.state === "minimized") {
          await chrome.windows.update(tab.windowId, { state: "normal", focused: true });
        } else {
          await chrome.windows.update(tab.windowId, { focused: true });
        }
      } catch (_) {}
      if (tab.active !== true) {
        try { await chrome.tabs.update(tabId, { active: true }); } catch (_) {}
      }
      await new Promise((resolve) => setTimeout(resolve, 450));
      return true;
    }
  } catch (_) {}
  return false;
}

// New composer selector: long answers add a second ProseMirror in the message
// area (aria "开始写作" / "Start writing"). The real composer is the one labelled
// 询问 / Ask ChatGPT inside the composer form, so match on aria label and form
// scope instead of a bare div.ProseMirror.
const COMPOSER_JS = "(function(){const byLabel=document.querySelector('div.ProseMirror[contenteditable=\\\"true\\\"][aria-label=\\\"询问 ChatGPT\\\"], div.ProseMirror[contenteditable=\\\"true\\\"][aria-label=\\\"Ask ChatGPT\\\"], [contenteditable=\\\"true\\\"][aria-label=\\\"询问 ChatGPT\\\"], [contenteditable=\\\"true\\\"][aria-label=\\\"Ask ChatGPT\\\"]'); if(byLabel) return byLabel; const inForm=document.querySelector('form[data-type=\\\"unified-composer\\\"] [contenteditable=\\\"true\\\"], #composer-background [contenteditable=\\\"true\\\"], [data-testid=\\\"composer\\\"] [contenteditable=\\\"true\\\"], form [contenteditable=\\\"true\\\"]'); if(inForm) return inForm; const all=Array.from(document.querySelectorAll('main [contenteditable=\\\"true\\\"]')); return all.find(el=>!/开始写作|Start writing|写入|Write/.test(el.getAttribute('aria-label')||'')) || document.querySelector('#prompt-textarea, textarea[data-id=\\\"root\\\"]') || null;})()";

function cdpCommand(tabId, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params || {}, (result) => {
      const err = chrome.runtime.lastError;
      if (err) reject(bridgeError("CDP_FAILED", String(err.message))); else resolve(result || {});
    });
  });
}

async function cdpFocusEditor(tabId) {
  await cdpCommand(tabId, "Runtime.evaluate", {
    expression: `const e=${COMPOSER_JS}; if(e){e.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r);} true`,
    returnByValue: true,
  });
}

async function cdpCaretAtEnd(tabId) {
  await cdpCommand(tabId, "Runtime.evaluate", {
    expression: `(function(){const e=${COMPOSER_JS}; if(!e) return false; e.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(e); r.collapse(false); s.removeAllRanges(); s.addRange(r); return true;})()`,
    returnByValue: true,
  });
}

async function cdpFocusComposerEnd(tabId) {
  await cdpCommand(tabId, "Runtime.evaluate", {
    expression: `(function(){const e=${COMPOSER_JS}; if(!e) return false; e.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(e); r.collapse(false); s.removeAllRanges(); s.addRange(r); return true;})()`,
    returnByValue: true,
  });
}

async function cdpReadEditorText(tabId) {
  const res = await cdpCommand(tabId, "Runtime.evaluate", {
    expression: `(function(){const e=${COMPOSER_JS}; return e ? e.innerText : ''})()`,
    returnByValue: true,
  });
  return String((res.result || {}).value || "");
}

let cdpLastLog = null;

async function cdpPressKey(tabId, key, code, vk, ctrl) {
  const modifiers = ctrl ? 2 : 0;
  await cdpCommand(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
  if (key === "Enter") await cdpCommand(tabId, "Input.dispatchKeyEvent", { type: "char", text: "\r", key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: 0 });
  await cdpCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
}

async function cdpTypeAndEnter(tabId, text) {
  const log = {};
  await debuggerAttach(tabId);
  try {
    // Window must be foreground: CDP key events are dropped in background windows.
    await ensureWindowForeground(tabId);
    await cdpFocusEditor(tabId);
    log.before = await cdpReadEditorText(tabId);
    // Select-all + insertText replaces the whole composer through the trusted
    // text-input pipe, which also syncs React/ProseMirror state (send enabled).
    await cdpCommand(tabId, "Runtime.evaluate", {
      expression: `(function(){const e=${COMPOSER_JS}; if(!e) return false; e.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r); return true;})()`,
      returnByValue: true,
    });
    await cdpCommand(tabId, "Input.insertText", { text: String(text || "") });
    await new Promise((resolve) => setTimeout(resolve, 400));
    log.afterInsert = await cdpReadEditorText(tabId);
    cdpLastLog = log;
    return true;
  } finally {
    await debuggerDetach(tabId);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === "bridge_message_event") {
      const targetId = targetIdForTab(sender.tab?.id);
      if (targetId) {
        const tab = await getBoundTab(targetId);
        sendToBridge(targetId, { ...message, type: "message_event", target_id: targetId, tab_title: tab?.title || "", tab_url: tab?.url || "" });
      }
      sendResponse({ success: true });
      return;
    }
    if (message.type === "bridge_progress") {
      const targetId = targetIdForTab(sender.tab?.id);
      if (targetId) sendToBridge(targetId, { ...message, type: "progress", target_id: targetId });
      sendResponse({ success: true });
      return;
    }
    if (message.type === "popup_status") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const targetId = targetIdForTab(tab?.id);
      sendResponse({ bridgeConnected: anySocketOpen(), tabBound: Boolean(targetId), targetId, pageReady: targetId ? await pageReady(tab.id) : false, tabTitle: tab?.title || "", busy: targetId ? activeRequests.has(targetId) : false, targetCount: Object.keys(boundTabs).length });
      return;
    }
    if (message.type === "bind_current_tab") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.url || !isChatGPTUrl(tab.url)) {
        sendResponse({ success: false, message: "当前页面不是 ChatGPT 网页" });
        return;
      }
      try {
        const result = await bindSpecificTab(tab.id);
        sendResponse({ success: true, targetId: result.target_id, title: result.title });
      } catch (error) {
        sendResponse({ success: false, message: error.detail || error.message || String(error) });
      }
      return;
    }
    if (message.type === "list_chatgpt_tabs") {
      const tabs = await chatgptTabs();
      sendResponse({ success: true, tabs: tabs.map((tab) => ({ ...tab, target_id: targetIdForTab(tab.tab_id) })) });
      return;
    }
    if (message.type === "reconnect") {
      for (const socket of sockets.values()) socket.close();
      connectBridge(CONTROL_TARGET_ID);
      for (const targetId of Object.keys(boundTabs)) connectBridge(targetId);
      sendResponse({ success: true });
    }
  })().catch((error) => sendResponse({ success: false, message: error.message }));
  return true;
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status !== "complete") return;
  const targetId = targetIdForTab(tabId);
  if (targetId) await sendStatus(targetId);
  autoBindSingleTab();
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const targetId = targetIdForTab(tabId);
  if (!targetId) return;
  delete boundTabs[targetId];
  await chrome.storage.local.set({ boundTabs });
  const socket = sockets.get(targetId);
  if (socket) socket.close();
  autoBindSingleTab();
});

chrome.tabs.onCreated.addListener(() => autoBindSingleTab());

chrome.runtime.onInstalled.addListener(() => connectBridge(CONTROL_TARGET_ID));
chrome.runtime.onStartup.addListener(() => connectBridge(CONTROL_TARGET_ID));
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "bridge-reconnect") return;
  connectBridge(CONTROL_TARGET_ID);
  await sendStatus(CONTROL_TARGET_ID);
  for (const targetId of Object.keys(boundTabs)) {
    connectBridge(targetId);
    await sendStatus(targetId);
  }
  await autoBindSingleTab();
});
