from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

ROLE_HINTS = {
    "user": "user",
    "human": "user",
    "assistant": "assistant",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
}

FILE_RE = re.compile(r"\b[\w./-]+\.(?:py|md|markdown|json|jsonl|yml|yaml|js|jsx|ts|tsx|java|kt|xml|html|css|scss|sh|bash|zsh|toml|ini|conf|properties|sql)\b")
CODE_FENCE_RE = re.compile(r"```(?:bash|sh|shell|zsh|cmd|powershell)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
INLINE_COMMAND_RE = re.compile(r"(?<!\w)((?:gh|git|rg|python3?|hexo|npm|node|curl|wget|printf|export|chmod|cp|mv|rm|cat|find|read)\b(?:\s+(?:--?[^\s`]+|\$?[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\"|'[^']+'|[^\s`]+)){1,12})")
ERROR_LINE_RE = re.compile(r"(?i)(error|failed|exception|traceback|not found|permission denied|timed out|timeout|denied|invalid|unauthorized)")
FAILED_ATTEMPT_RE = re.compile(
    r"(?i)(?:\btried\b|\battempted\b|\bfailed\b|\bdid not work\b|\bdidn't work\b|\bdoes not work\b|\bdoesn't work\b|\bno luck\b|\bstill failing\b|无效|失败|不行|没有解决|没解决|尝试过|尝试了|尝试使用)"
)
ROOT_CAUSE_RE = re.compile(r"(?i)(?:\broot cause\b|原因是|根因是|根因在于|核心问题是|主要原因是)")
FIX_RE = re.compile(r"(?i)(?:\bthe fix is\b|\bfix is\b|\bfix to\b|\bfix was\b|解决方案(?:是|为|在于)?|最终通过)")
ENV_PATTERNS = {
    "os": re.compile(r"(?i)\b(ubuntu|debian|centos|alpine|linux|macos|windows|android|ios)\b"),
    "runtime": re.compile(r"(?i)\b(python\s*\d+(?:\.\d+)*|node(?:\.js)?\s*\d+(?:\.\d+)*|java\s*\d+(?:\.\d+)*|jdk\s*\d+(?:\.\d+)*|npm\s*\d+(?:\.\d+)*)\b"),
    "tools": re.compile(r"(?i)\b(openclaw|codex|hexo|git|github actions|github|docker|maven|gradle)\b"),
}

HOST_SOURCE_ALIASES = {
    "current-session",
    "openclaw-current-session",
    "openclaw-session",
    "openclaw-session-history",
}

DEFAULT_SECTION_ORDER = [
    "background",
    "symptoms",
    "investigation",
    "root_cause",
    "fix",
    "environment",
    "files",
    "commands",
    "lesson",
]

DEFAULT_SECTION_HEADINGS = {
    "background": "背景",
    "symptoms": "问题现象",
    "investigation": "排查过程",
    "root_cause": "根因判断",
    "fix": "解决方案",
    "environment": "环境信息",
    "files": "涉及文件",
    "commands": "关键命令",
    "lesson": "复盘与经验",
}


@dataclass
class Message:
    role: str
    text: str
    timestamp: str | None = None


@dataclass
class SessionSnapshot:
    source: str
    session_id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    environment: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class IssueContext:
    topic: str
    summary: str
    symptoms: list[str] = field(default_factory=list)
    investigation_steps: list[str] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)
    root_cause: str = "尚未自动确认"
    fix: str = "尚未自动确认"
    files_changed: list[str] = field(default_factory=list)
    commands_used: list[str] = field(default_factory=list)
    environment: dict[str, list[str]] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceRequest:
    path: str | None
    source: str
    base_dir: str | None = None
    session_key: str | None = None


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = normalize_space(raw)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text: str, limit: int = 120) -> str:
    text = normalize_space(text)
    if not text:
        return ""
    pieces = re.split(r"(?<=[。！？.!?])\s+", text)
    candidate = pieces[0]
    return candidate[:limit].rstrip()


def safe_title(text: str) -> str:
    text = normalize_space(text)
    if not text:
        return "agent-blogger-post"
    text = text[:80]
    text = re.sub(r"[\r\n]+", " ", text)
    return text


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or datetime.now().strftime("post-%Y%m%d-%H%M%S")


def text_from_any(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(part for part in (text_from_any(item) for item in value) if part)
    if isinstance(value, dict):
        preferred_keys = [
            "text",
            "content",
            "message",
            "body",
            "input",
            "output",
            "reasoning",
            "summary",
            "value",
        ]
        for key in preferred_keys:
            if key in value:
                text = text_from_any(value[key])
                if text:
                    return text
        for key in ("parts", "blocks", "segments", "items"):
            if key in value:
                text = text_from_any(value[key])
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def detect_role(entry: dict[str, Any]) -> str:
    candidates = [
        entry.get("role"),
        entry.get("author"),
        entry.get("sender"),
        entry.get("participant"),
        entry.get("type"),
        entry.get("kind"),
    ]
    message = entry.get("message")
    if isinstance(message, dict):
        candidates.extend([message.get("role"), message.get("author"), message.get("sender")])
    for candidate in candidates:
        if not candidate:
            continue
        normalized = str(candidate).lower()
        if normalized in ROLE_HINTS:
            return ROLE_HINTS[normalized]
        if "assistant" in normalized or normalized in {"model", "agent"}:
            return "assistant"
        if "user" in normalized or "human" in normalized:
            return "user"
        if "tool" in normalized:
            return "tool"
        if "system" in normalized:
            return "system"
    return "assistant"


def extract_message_text(entry: dict[str, Any]) -> str:
    direct_keys = ["text", "content", "body", "output"]
    for key in direct_keys:
        if key in entry:
            text = text_from_any(entry[key])
            if text:
                return text
    message = entry.get("message")
    if message is not None:
        text = text_from_any(message)
        if text:
            return text
    data = entry.get("data")
    if data is not None:
        text = text_from_any(data)
        if text:
            return text
    return ""


def safe_format_template(template: str, values: dict[str, str]) -> str:
    try:
        return template.format(**values)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(f"unknown template variable: {missing}") from exc
