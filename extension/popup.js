const $ = (id) => document.getElementById(id);

function setState(id, value, yes, no) {
  $(id).textContent = value ? yes : no;
  $(id).className = value ? "ok" : "bad";
}

async function refresh() {
  const status = await chrome.runtime.sendMessage({ type: "popup_status" });
  setState("bridge", status?.bridgeConnected, "已连接", "未连接");
  setState("tab", status?.tabBound, "已绑定", "未绑定");
  setState("page", status?.pageReady, "已就绪", "未就绪");
  $("busy").textContent = status?.busy ? "处理中" : "空闲";
  $("busy").className = status?.busy ? "warn" : "ok";
  $("targets").textContent = String(status?.targetCount || 0);
  if (!status?.bridgeConnected) {
    $("detail").textContent = "Bridge 未连接：请启动 scripts/start_bridge.ps1";
  } else if (!status?.tabBound) {
    $("detail").textContent = "请打开 ChatGPT 标签页并点击绑定按钮";
  } else if (!status?.pageReady) {
    $("detail").textContent = "标签页已绑定，但页面脚本未就绪；请刷新 ChatGPT 页面";
  } else {
    $("detail").textContent = `已就绪：${status.tabTitle || "ChatGPT"} · ${status.targetId || "目标"}`;
  }
}

$("bind").addEventListener("click", async () => {
  const result = await chrome.runtime.sendMessage({ type: "bind_current_tab" });
  $("detail").textContent = result?.success ? `已绑定：${result.title} · ${result.targetId || "目标"}` : (result?.message || "绑定失败");
  await refresh();
});

$("reconnect").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "reconnect" });
  setTimeout(refresh, 500);
});

refresh().catch((error) => { $("detail").textContent = error.message; });
