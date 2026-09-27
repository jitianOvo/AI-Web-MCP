let activeRequestId = "";
let cancelledRequestId = "";
const sentMessageKeys = new Set();
let streamingNotified = false;
let pendingBufferedMessages = new Map();
const domMessageIds = new WeakMap();
let nextDomMessageId = 1;

function firstMatch(selectors) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element) return element;
  }
  return null;
}

function cleanText(node) {
  const clone = node.cloneNode(true);
  clone.querySelectorAll("button, nav, [aria-hidden='true']").forEach((item) => item.remove());
  return (clone.innerText || clone.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

function messageNodes() {
  const nodes = [];
  for (const selector of [...GPT_WEB_SELECTORS.userMessage, ...GPT_WEB_SELECTORS.assistantMessage]) {
    document.querySelectorAll(selector).forEach((node) => nodes.push(node));
  }
  if (nodes.length) return Array.from(new Set(nodes));
  for (const selector of GPT_WEB_SELECTORS.conversationTurn || []) {
    document.querySelectorAll(selector).forEach((node) => nodes.push(node));
  }
  return Array.from(new Set(nodes)).filter((node) => cleanText(node));
}

function roleFromNode(node) {
  const roleNode = node.matches?.("[data-message-author-role]")
    ? node
    : node.querySelector?.("[data-message-author-role]");
  const explicit = roleNode?.getAttribute("data-message-author-role");
  if (explicit) return explicit;
  const marker = `${node.getAttribute?.("data-testid") || ""} ${node.getAttribute?.("aria-label") || ""} ${String(node.className || "")}`.toLowerCase();
  if (marker.includes("user")) return "user";
  if (marker.includes("assistant") || marker.includes("conversation-turn")) return "assistant";
  return "unknown";
}

function messageFromNode(node) {
  const role = roleFromNode(node);
  const content = cleanText(node);
  if (!content) return null;
  const container = node.closest("[data-message-id]") || node.closest("article") || node;
  let messageId = container.getAttribute("data-message-id");
  if (!messageId) {
    messageId = domMessageIds.get(container);
    if (!messageId) {
      messageId = `dom-${role}-${nextDomMessageId++}`;
      domMessageIds.set(container, messageId);
    }
  }
  if (String(messageId).startsWith("request-placeholder")) return null;
  const contentHash = `${role}:${content}`;
  return { message_id: messageId, role, content, content_hash: contentHash };
}

function answerNodes() {
  return messageNodes().filter((node) => {
    const role = roleFromNode(node);
    if (!["assistant", "unknown"].includes(role)) return false;
    const container = node.closest("[data-message-id]") || node.closest("article") || node;
    const id = container.getAttribute("data-message-id");
    return !(id && String(id).startsWith("request-placeholder"));
  });
}

function conversationId() {
  const match = location.pathname.match(/\/c\/([^/]+)/);
  return match ? match[1] : "current";
}

function progress(requestId, stage) {
  chrome.runtime.sendMessage({ type: "bridge_progress", request_id: String(requestId), stage }).catch(() => {});
}

function isNewChatState() {
  const onHome = location.pathname === "/" || location.pathname === "";
  return onHome && answerNodes().length === 0 && Boolean(firstMatch(GPT_WEB_SELECTORS.input));
}

function domSnapshot() {
  const input = firstMatch(GPT_WEB_SELECTORS.input);
  const sendMatches = GPT_WEB_SELECTORS.sendButton.map((selector) => {
    const el = document.querySelector(selector);
    if (!el) return { selector, found: false };
    return {
      selector, found: true, tag: el.tagName,
      testid: el.getAttribute("data-testid") || "",
      aria: el.getAttribute("aria-label") || "",
      type: el.getAttribute("type") || "",
      disabled: Boolean(el.disabled),
      visible: Boolean(el.offsetParent),
    };
  });
  const stopMatches = GPT_WEB_SELECTORS.stopButton.map((selector) => Boolean(document.querySelector(selector)));
  return {
    url: location.href, path: location.pathname, readyState: document.readyState,
    input_selector_hit: GPT_WEB_SELECTORS.input.findIndex((selector) => Boolean(document.querySelector(selector))),
    input_tag: input ? input.tagName : "", input_id: input ? input.id : "",
    input_contenteditable: input ? input.getAttribute("contenteditable") : null,
    prompt_textarea_exists: Boolean(document.querySelector("#prompt-textarea")),
    send_matches: sendMatches, stop_matches: stopMatches,
  };
}

function domDetail() {
  const contenteditables = Array.from(document.querySelectorAll("main [contenteditable='true']")).map((el, index) => {
    const form = el.closest("form");
    return {
      index, tag: el.tagName, id: el.id || "", cls: String(el.className || "").slice(0, 120),
      aria: el.getAttribute("aria-label") || "", placeholder: el.getAttribute("data-placeholder") || "",
      lexical: el.getAttribute("data-lexical-editor"), inside_form: Boolean(form),
      form_id: form ? form.id : "", form_data_type: form ? form.getAttribute("data-type") : "", form_action: form ? form.getAttribute("action") : "",
      text_len: cleanText(el).length,
    };
  });
  const textareas = Array.from(document.querySelectorAll("main textarea")).map((el, index) => ({
    index, id: el.id || "", placeholder: el.getAttribute("placeholder") || "", rows: el.getAttribute("rows") || "",
  }));
  const forms = Array.from(document.querySelectorAll("form")).map((el, index) => ({
    index, id: el.id || "", cls: String(el.className || "").slice(0, 80),
    data_type: el.getAttribute("data-type") || "", submits: el.querySelectorAll("button[type='submit']").length,
    buttons: el.querySelectorAll("button").length,
  }));
  return { contenteditables, textareas, forms };
}

async function startNewChat() {
  if (isNewChatState()) return { already: true, conversation_id: conversationId() };
  const button = firstMatch(GPT_WEB_SELECTORS.newChatButton);
  if (!button) throw bridgeError("NEW_CHAT_NOT_FOUND", "没有找到新聊天入口");
  button.click();
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    if (isNewChatState()) return { already: false, conversation_id: conversationId() };
    await delay(250);
  }
  throw bridgeError("NEW_CHAT_TIMEOUT", "进入新聊天超时");
}

async function waitForUserMessage(prompt, timeoutMs = 10000) {
  const norm = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const needle = norm(String(prompt || "").slice(0, 600));
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const userNodes = messageNodes().filter((node) => roleFromNode(node) === "user");
    for (const node of userNodes) {
      const text = cleanText(node);
      if (text && (!needle || norm(text).includes(needle))) return true;
    }
    if (userNodes.some((node) => cleanText(node))) return true;
    await delay(200);
  }
  return false;
}

function emitNewMessages() {
  for (const node of messageNodes()) {
    const message = messageFromNode(node);
    if (!message) continue;
    const key = `${message.message_id}:${message.content_hash}`;
    if (sentMessageKeys.has(key)) continue;
    if (activeRequestId) {
      pendingBufferedMessages.set(key, message);
      while (pendingBufferedMessages.size > 500) pendingBufferedMessages.delete(pendingBufferedMessages.keys().next().value);
      continue;
    }
    sentMessageKeys.add(key);
    while (sentMessageKeys.size > 500) sentMessageKeys.delete(sentMessageKeys.values().next().value);
    chrome.runtime.sendMessage({ type: "bridge_message_event", conversation_id: conversationId(), message }).catch(() => {});
  }
}

async function flushBufferedMessages() {
  const conversation = conversationId();
  const entries = Array.from(pendingBufferedMessages.values());
  const ordered = [...entries.filter((message) => message.role === "user"), ...entries.filter((message) => message.role !== "user")];
  const sends = [];
  for (const message of ordered) {
    const key = `${message.message_id}:${message.content_hash}`;
    if (sentMessageKeys.has(key)) continue;
    sentMessageKeys.add(key);
    sends.push(chrome.runtime.sendMessage({ type: "bridge_message_event", conversation_id: conversation, message }).catch(() => {}));
  }
  pendingBufferedMessages = new Map();
  await Promise.allSettled(sends);
}

const observer = new MutationObserver(() => emitNewMessages());
observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
setTimeout(emitNewMessages, 1000);

function setPrompt(input, prompt) {
  input.focus();
  if (input instanceof HTMLTextAreaElement || input instanceof HTMLInputElement) {
    const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value");
    if (descriptor?.set) descriptor.set.call(input, prompt); else input.value = prompt;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(input);
  selection.removeAllRanges();
  selection.addRange(range);
  document.execCommand("insertText", false, prompt);
  input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: prompt }));
}

function isProseMirror(input) {
  return Boolean(input && String(input.className || "").includes("ProseMirror"));
}

function inputValue(input) {
  if (!input) return "";
  if (input instanceof HTMLTextAreaElement || input instanceof HTMLInputElement) return input.value || "";
  return cleanText(input);
}

async function setPromptVerified(input, prompt) {
  setPrompt(input, prompt);
  await delay(150);
  const needle = String(prompt || "").trim().slice(0, 24);
  if (inputValue(input).includes(needle)) return true;
  if (isProseMirror(input)) {
    input.focus();
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(input);
    selection.removeAllRanges();
    selection.addRange(range);
    const transfer = new DataTransfer();
    transfer.setData("text/plain", prompt);
    input.dispatchEvent(new ClipboardEvent("paste", { clipboardData: transfer, bubbles: true, cancelable: true }));
  } else {
    input.focus();
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(input);
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand("insertText", false, prompt);
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: prompt }));
  }
  await delay(150);
  return inputValue(input).includes(needle);
}

async function waitForInput(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const input = firstMatch(GPT_WEB_SELECTORS.input);
    if (input && !input.hasAttribute("disabled")) return input;
    await delay(250);
  }
  throw bridgeError("INPUT_NOT_FOUND", "没有找到 ChatGPT 输入框");
}

async function clickSend() {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    if (clickSendWithFallback()) return;
    await delay(200);
  }
  throw bridgeError("SEND_FAILED", "没有找到可点击的发送按钮");
}

function clickSendWithFallback() {
  const input = firstMatch(GPT_WEB_SELECTORS.input);
  if (pressEnterToSend(input)) return true;
  const button = firstMatch(GPT_WEB_SELECTORS.sendButton);
  if (button && !button.disabled && button.getAttribute("aria-disabled") !== "true") { button.click(); return true; }
  const form = input?.closest?.("form");
  if (form) {
    const submit = form.querySelector("button[type='submit']");
    if (submit && !submit.disabled) { submit.click(); return true; }
    if (typeof form.requestSubmit === "function") { form.requestSubmit(); return true; }
  }
  return false;
}

function pressEnterToSend(input, ctrl = false) {
  if (!input) return false;
  input.focus();
  const options = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true, composed: true, ctrlKey: Boolean(ctrl), metaKey: Boolean(ctrl) };
  input.dispatchEvent(new KeyboardEvent("keydown", options));
  input.dispatchEvent(new KeyboardEvent("keypress", options));
  input.dispatchEvent(new KeyboardEvent("keyup", options));
  return true;
}
async function waitForAnswer(requestId, baselineCount, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastText = "";
  let stableSince = 0;
  while (Date.now() < deadline) {
    if (cancelledRequestId === requestId) throw bridgeError("REQUEST_CANCELLED", "请求已取消");
    const messages = answerNodes();
    if (messages.length > baselineCount) {
      const text = cleanText(messages[messages.length - 1]);
      if (text !== lastText) { lastText = text; stableSince = Date.now(); }
      const generating = Boolean(firstMatch(GPT_WEB_SELECTORS.stopButton));
      if (lastText && !streamingNotified) { streamingNotified = true; progress(requestId, "STREAMING"); }
      const complex = lastText.length > 2000 || /```|\|\s*-|^#+\s/m.test(lastText);
      const stableWindow = complex ? 1200 : 600;
      if (lastText && !generating && Date.now() - stableSince >= stableWindow) {
        progress(requestId, "STABILIZING");
        return lastText;
      }
      if (lastText && Date.now() - stableSince >= 8000) { progress(requestId, "STABILIZING"); return lastText; }
    }
    await delay(300);
  }
  throw bridgeError("RESPONSE_TIMEOUT", "ChatGPT 回答超时");
}


function formButtonsSnapshot() {
  const input = firstMatch(GPT_WEB_SELECTORS.input);
  const form = input?.closest?.("form");
  if (!form) return [];
  return Array.from(form.querySelectorAll("button")).map((b, i) => ({
    i, aria: b.getAttribute("aria-label") || "", testid: b.getAttribute("data-testid") || "",
    disabled: Boolean(b.disabled), aria_disabled: b.getAttribute("aria-disabled") || "",
    visible: Boolean(b.offsetParent), text: (b.textContent || "").trim().slice(0, 20),
  }));
}

async function executeTask(message) {
  const requestId = String(message.request_id || "");
  if (activeRequestId) throw bridgeError("EXTENSION_BUSY", "当前页面仍在处理上一项任务");
  activeRequestId = requestId;
  cancelledRequestId = "";
  streamingNotified = false;
  try {
    progress(requestId, "CREATED");
    const input = await waitForInput();
    progress(requestId, "INPUT_READY");
    if (["cdp", "verify"].includes(String(message.input_backend || ""))) {
      progress(requestId, "INPUT_SENT");
      const baselineCount = answerNodes().length;
      const acked = await waitForUserMessage(String(message.prompt || ""), 15000);
      if (!acked) throw bridgeError("SEND_FAILED", "用户消息未在页面确认上屏; cdp=true");
      progress(requestId, "USER_MESSAGE_CONFIRMED");
      const result = await waitForAnswer(requestId, baselineCount, Number(message.timeout_ms || 600000));
      const assistantNodes = answerNodes();
      const lastMessage = assistantNodes.length ? messageFromNode(assistantNodes[assistantNodes.length - 1]) : null;
      progress(requestId, "COMPLETED");
      await flushBufferedMessages();
      return { success: true, result, conversation_id: conversationId(), message_id: lastMessage?.message_id || `assistant-${Date.now()}` };
    }
    if (String(message.input_backend) === "send_only") {
      progress(requestId, "INPUT_SENT");
      const baselineCount = answerNodes().length;
      await clickSend();
      progress(requestId, "SEND_CLICKED");
      const acked = await waitForUserMessage(String(message.prompt || ""), 15000);
      if (!acked) throw bridgeError("SEND_FAILED", "用户消息未在页面确认上屏; send_only=true");
      progress(requestId, "USER_MESSAGE_CONFIRMED");
      const result = await waitForAnswer(requestId, baselineCount, Number(message.timeout_ms || 600000));
      const assistantNodes = answerNodes();
      const lastMessage = assistantNodes.length ? messageFromNode(assistantNodes[assistantNodes.length - 1]) : null;
      progress(requestId, "COMPLETED");
      await flushBufferedMessages();
      return { success: true, result, conversation_id: conversationId(), message_id: lastMessage?.message_id || `assistant-${Date.now()}` };
    }
    const baselineCount = answerNodes().length;
    const written = await setPromptVerified(input, String(message.prompt || ""));
    if (!written) throw bridgeError("INPUT_WRITE_FAILED", "内容未能写入输入框");
    await delay(250);
    const promptText = String(message.prompt || "");
    const editorTextBeforeSend = inputValue(input);
    const sendButtonEl = document.querySelector("button[aria-label='发送'], button[aria-label*='Send'], button[data-testid='composer-send-button'], button[data-testid='send-button']");
    const sendButtonHtml = sendButtonEl ? String(sendButtonEl.outerHTML).slice(0, 300) : "none";
    const preButtons = formButtonsSnapshot();
    const attempts = [];
    const sendMethods = [
      { name: "send_button", run: () => {
        const button = document.querySelector("button[aria-label*='发送'], button[aria-label*='Send'], button[data-testid='composer-send-button'], button[data-testid='send-button']");
        if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return false;
        button.click(); return true;
      } },
      { name: "enter", run: () => pressEnterToSend(input, false) },
      { name: "ctrl_enter", run: () => pressEnterToSend(input, true) },
      { name: "form_submit", run: () => {
        const form = input?.closest?.("form");
        if (!form || typeof form.requestSubmit !== "function") return false;
        form.requestSubmit(); return true;
      } },
    ];
    let acked = false;
    for (const method of sendMethods) {
      const fired = method.run();
      progress(requestId, "SUBMITTED");
      if (fired) acked = await waitForUserMessage(promptText, 3000);
      attempts.push({ method: method.name, fired, input_text_after: inputValue(input), url_after: location.href });
      if (acked) break;
    }
    if (!acked) {
      const sentByClear = inputValue(input) === "" && attempts.some((item) => item.fired);
      if (sentByClear) acked = await waitForUserMessage(promptText, 4000);
      if (!acked) {
        const snapshot = JSON.stringify({ editor_text_before_send: editorTextBeforeSend, send_button_html: sendButtonHtml, pre_buttons: preButtons, attempts, form_buttons: formButtonsSnapshot(), user_nodes: messageNodes().filter((n) => roleFromNode(n) === "user").length, answer_nodes: answerNodes().length, url: location.href });
        throw bridgeError("SEND_FAILED", "用户消息未在页面确认上屏; snapshot=" + snapshot);
      }
    }
    progress(requestId, "USER_MESSAGE_CONFIRMED");
    let result;
    try {
      result = await waitForAnswer(requestId, baselineCount, Number(message.timeout_ms || 600000));
    } catch (error) {
      const snapshot = JSON.stringify({ editor_text_before_send: editorTextBeforeSend, send_button_html: sendButtonHtml, attempts, user_nodes: messageNodes().filter((n) => roleFromNode(n) === "user").length, answer_nodes: answerNodes().length, input_text_now: inputValue(input), url: location.href });
      throw bridgeError(error.code || "RESPONSE_TIMEOUT", (error.message || "回答超时") + "; snapshot=" + snapshot);
    }
    const assistantNodes = answerNodes();
    const lastMessage = assistantNodes.length ? messageFromNode(assistantNodes[assistantNodes.length - 1]) : null;
    progress(requestId, "COMPLETED");
    await flushBufferedMessages();
    return { success: true, result, conversation_id: conversationId(), message_id: lastMessage?.message_id || `assistant-${Date.now()}` };
  } finally {
    activeRequestId = "";
    flushBufferedMessages().catch(() => {});
    setTimeout(emitNewMessages, 500);
  }
}

function cancelTask(requestId) {
  if (activeRequestId === requestId) {
    cancelledRequestId = requestId;
    const stop = firstMatch(GPT_WEB_SELECTORS.stopButton);
    if (stop) stop.click();
  }
}

function bridgeError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "bridge_ping") {
  if (message.type === "bridge_focus_editor") {
    const input = firstMatch(GPT_WEB_SELECTORS.input);
    if (input) {
      input.focus();
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(input);
      selection.removeAllRanges();
      selection.addRange(range);
    }
    sendResponse({ success: true });
    return false;
  }
    sendResponse({ ready: Boolean(firstMatch(GPT_WEB_SELECTORS.input)), url: location.href });
    return false;
  }
  if (message.type === "bridge_state") {
    const messages = messageNodes().filter((node) => ["assistant", "unknown"].includes(roleFromNode(node)));
    const latest = messages.length ? messageFromNode(messages[messages.length - 1]) : null;
    sendResponse({
      ready: Boolean(firstMatch(GPT_WEB_SELECTORS.input)),
      url: location.href,
      generating: Boolean(firstMatch(GPT_WEB_SELECTORS.stopButton)),
      latest_message: latest ? latest.content : "",
      conversation_title: document.title || "",
    });
    return false;
  }
  if (message.type === "bridge_check_state") {
    const nodes = messageNodes();
    const userNodes = nodes.filter((node) => roleFromNode(node) === "user");
    const assistantNodes = answerNodes();
    const lastAssistant = assistantNodes.length ? cleanText(assistantNodes[assistantNodes.length - 1]) : "";
    const needle = String(message.prompt || "").trim().slice(0, 40);
    const userOnScreen = userNodes.some((node) => {
      const text = cleanText(node);
      return text && (!needle || text.includes(needle));
    });
    sendResponse({
      success: true,
      user_message_on_screen: userOnScreen,
      assistant_present: assistantNodes.length > 0,
      last_text: lastAssistant,
      generating: Boolean(firstMatch(GPT_WEB_SELECTORS.stopButton)),
      page_ready: true,
      input_ready: Boolean(firstMatch(GPT_WEB_SELECTORS.input)),
      is_new_chat: isNewChatState(),
      conversation_id: conversationId(),
      url: location.href,
      input_text: inputValue(firstMatch(GPT_WEB_SELECTORS.input)),
      dom: domSnapshot(),
      dom_detail: domDetail(),
    });
    return false;
  }
  if (message.type === "bridge_check_image_upload") {
    const composer = firstMatch(GPT_WEB_SELECTORS.input);
    let images = [];
    let uploading = false;
    let textLength = 0;
    let hasContent = false;
    if (composer) {
      images = Array.from(composer.querySelectorAll("img, [data-testid*='image'], [class*='thumbnail'], [class*='attachment']"));
      uploading = Boolean(composer.querySelector("[data-testid*='upload'], [class*='uploading'], [aria-busy='true'], [data-state*='uploading']"));
      textLength = (composer.innerText || "").length;
      hasContent = images.length > 0 || composer.children.length > 0 || textLength > 0;
    }
    const imageCount = images.length;
    const ready = hasContent && !uploading;
    sendResponse({ success: true, image_count: imageCount, uploading, ready, text_length: textLength, has_content: hasContent });
    return false;
  }
  if (message.type === "bridge_new_chat") {
    startNewChat().then((result) => sendResponse({ success: true, ...result })).catch((error) => sendResponse({ success: false, code: error.code || "NEW_CHAT_FAILED", message: error.message }));
    return true;
  }
  if (message.type === "bridge_cancel") {
    cancelTask(String(message.request_id || ""));
    sendResponse({ success: true });
    return false;
  }
  if (message.type === "bridge_sync") {
    sendResponse({
      success: true,
      conversation_id: conversationId(),
      messages: messageNodes().map(messageFromNode).filter(Boolean),
    });
    return false;
  }
  if (message.type === "bridge_task") {
    executeTask(message).then(sendResponse).catch((error) => sendResponse({ success: false, code: error.code || "EXTENSION_ERROR", message: error.message }));
    return true;
  }
  return false;
});
