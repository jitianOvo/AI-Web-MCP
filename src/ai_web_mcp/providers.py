"""Small provider catalog and strict browser conversation URL identities."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit


PROVIDERS = {
    "chatgpt": {"name": "ChatGPT", "url": "https://chatgpt.com/"},
    "glm": {"name": "GLM", "url": "https://chatglm.cn/main/alltoolsdetail"},
}


def canonical_provider(provider: str, allow_empty: bool = False) -> str:
    value = str(provider or "").lower().strip()
    if value == "gpt":
        value = "chatgpt"
    if not value and allow_empty:
        return ""
    if value not in PROVIDERS:
        raise ValueError("provider 必须是 chatgpt（别名 gpt）或 glm")
    return value


def detect_provider(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme == "https":
            if parsed.netloc in {"chatgpt.com", "chat.openai.com"}:
                return "chatgpt"
            if parsed.netloc == "chatglm.cn":
                return "glm"
    except ValueError:
        pass
    return ""


def normalize_ai_url(provider: str, url: str = "", require_conversation: bool = False) -> str:
    provider = canonical_provider(provider)
    if not isinstance(url, str) or any(ord(char) <= 32 for char in url) or "\\" in url:
        raise ValueError("必须提供完整官方 HTTPS 会话 URL")
    parsed = urlsplit(url or PROVIDERS[provider]["url"])
    if detect_provider(parsed.geturl()) != provider or parsed.fragment:
        raise ValueError("仅接受指定提供方的官方 HTTPS 会话 URL，不带片段、端口或登录信息")
    path = parsed.path.rstrip("/")
    if provider == "chatgpt":
        if parsed.query:
            raise ValueError("ChatGPT 会话 URL 不接受查询参数")
        if not re.fullmatch(r"(?:/g/[A-Za-z0-9_-]+)?/c/[A-Za-z0-9_-]+", path):
            if path or require_conversation:
                raise ValueError("历史会话 URL 必须包含 /c/<conversation_id>")
        return f"https://{parsed.netloc}{path or '/'}"
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    ids = [value for key, value in pairs if key == "cid"]
    if (path != "/main/alltoolsdetail" or any(key not in {"cid", "t", "lang"} for key, _ in pairs)
            or len(ids) > 1 or (ids and not re.fullmatch(r"[A-Za-z0-9_-]+", ids[0]))
            or (require_conversation and not ids)):
        raise ValueError("GLM 会话 URL 必须为 /main/alltoolsdetail，历史会话使用 cid 参数")
    query = urlencode(pairs)
    return f"https://chatglm.cn{path}" + (f"?{query}" if query else "")


def conversation_id_from_url(provider: str, url: str) -> str:
    parsed = urlsplit(normalize_ai_url(provider, url))
    if canonical_provider(provider) == "glm":
        return dict(parse_qsl(parsed.query)).get("cid", "")
    match = re.search(r"/c/([A-Za-z0-9_-]+)$", parsed.path)
    return match.group(1) if match else ""


def conversation_urls_match(provider: str, candidate: str, destination: str) -> bool:
    try:
        first, second = normalize_ai_url(provider, candidate), normalize_ai_url(provider, destination)
        if canonical_provider(provider) == "glm":
            return conversation_id_from_url(provider, first) == conversation_id_from_url(provider, second)
        return first == second
    except (ValueError, TypeError):
        return False


def list_provider_capabilities() -> list[dict]:
    return [{"provider": key, **value, "aliases": ["gpt"] if key == "chatgpt" else [],
             "capabilities": ["text", "vision", "upload_image", "send_attachments", "open_conversation", "new_chat"]}
            for key, value in PROVIDERS.items()]
