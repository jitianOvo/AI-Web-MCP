globalThis.GPT_WEB_SELECTORS = Object.freeze({
  input: [
    // New composer (ProseMirror) is identified by its aria label and being
    // inside the composer form.  Long answers add a second ProseMirror
    // ("开始写作" / "Start writing") in the message area that must not win.
    "div.ProseMirror[contenteditable='true'][aria-label='询问 ChatGPT']",
    "div.ProseMirror[contenteditable='true'][aria-label='Ask ChatGPT']",
    "[contenteditable='true'][aria-label='询问 ChatGPT']",
    "[contenteditable='true'][aria-label='Ask ChatGPT']",
    "#prompt-textarea",
    "textarea[data-id='root']",
    "[contenteditable='true'][data-lexical-editor='true']",
    "form[data-type='unified-composer'] [contenteditable='true']",
    "[data-testid='composer'] [contenteditable='true']",
    "#composer-background [contenteditable='true']",
    "form [contenteditable='true']",
    "main textarea[placeholder]",
    "main [contenteditable='true']"
  ],
  sendButton: [
    "button[data-testid='send-button']",
    "button[aria-label='Send prompt']",
    "button[aria-label*='Send']",
    "button[aria-label='发送消息']",
    "button[aria-label*='发送']",
    "form button[type='submit']"
    ,"button[data-testid='composer-send-button']"
    ,"button[aria-label*='Submit']"
    ,"form[data-type='unified-composer'] button[type='submit']"
  ],
  stopButton: [
    "button[data-testid='stop-button']",
    "button[aria-label='Stop streaming']",
    "button[aria-label='Stop generating']",
    "button[aria-label='停止生成']",
    "button[aria-label='停止回应']"
  ],
  newChatButton: [
    "a[href='/']", 
    "a[href='https://chatgpt.com/']",
    "[data-testid='new-chat']",
    "button[aria-label*='新聊天']",
    "button[aria-label*='New chat']",
    "a[aria-label*='新聊天']",
    "a[aria-label*='New chat']"
  ],
  userMessage: ["[data-message-author-role='user']"],
  userMessage: [
    "[data-message-author-role='user']",
    "[class*='bg-user-message']"
  ],
  assistantMessage: [
    "[data-message-author-role='assistant']",
    "[data-chatgpt-selection-message-id]"  // new UI: assistant message node keeps its own selection id
  ],
  conversationTurn: [
    "[data-testid^='conversation-turn-']",
    "main article"
  ],
  pageError: ["main [role='alert']", "main [aria-live='assertive']"]
});
