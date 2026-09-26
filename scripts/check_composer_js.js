// Validate the COMPOSER_JS expression embedded in extension/background.js.
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "extension", "background.js"), "utf8");
const match = src.match(/const COMPOSER_JS = "(.*)";\r?\n/s);
if (!match) {
  console.log("RESULT: NO_MATCH");
  process.exit(1);
}

// Unescape the JS string literal exactly the way the JS engine would.
const composerJs = JSON.parse(`"${match[1]}"`);

console.log("COMPOSER_JS length:", composerJs.length);
try {
  // eslint-disable-next-line no-new-func
  new Function(composerJs);
  console.log("RESULT: PARSE_OK");
} catch (error) {
  console.log("RESULT: PARSE_ERROR", error.message);
  process.exit(1);
}

// Simulate the DOM: long answer page with a "开始写作" ProseMirror and the real composer.
const fakeDocument = {
  querySelector(selector) {
    if (selector.includes("aria-label=\\\"询问 ChatGPT\\\"")) {
      return { id: "real-composer", text: "" };
    }
    if (selector === "form [contenteditable=\\\"true\\\"]" || selector.includes("form[data-type")) {
      return null;
    }
    if (selector.includes("#prompt-textarea")) {
      return null;
    }
    return null;
  },
  querySelectorAll(selector) {
    if (selector.includes("main [contenteditable")) {
      return [
        { getAttribute: () => "开始写作", id: "write-helper" },
        { getAttribute: () => "询问 ChatGPT", id: "real-composer" },
      ];
    }
    return [];
  },
};

const fn = new Function("document", `return ${composerJs};`);
const picked = fn(fakeDocument);
console.log("RESULT: PICKED", picked && picked.id);
