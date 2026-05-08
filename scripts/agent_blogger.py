#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import yaml
except ImportError:  # pragma: no cover - optional at runtime
    yaml = None
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
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
INLINE_COMMAND_RE = re.compile(r"(?<!\w)((?:gh|git|python3?|hexo|npm|node|curl|wget|printf|export|chmod|cp|mv|rm|cat|find|read)\b(?:\s+(?:--?[A-Za-z0-9_./:=+$-]+|\$?[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\"|'[^']+'|[A-Za-z0-9_./:=+$-]+)){1,12})")
ERROR_LINE_RE = re.compile(r"(?i)(error|failed|exception|traceback|not found|permission denied|timed out|timeout|denied|invalid|unauthorized)")
ENV_PATTERNS = {
    "os": re.compile(r"(?i)\b(ubuntu|debian|centos|alpine|linux|macos|windows|android|ios)\b"),
    "runtime": re.compile(r"(?i)\b(python\s*\d+(?:\.\d+)*|node(?:\.js)?\s*\d+(?:\.\d+)*|java\s*\d+(?:\.\d+)*|jdk\s*\d+(?:\.\d+)*|npm\s*\d+(?:\.\d+)*)\b"),
    "tools": re.compile(r"(?i)\b(openclaw|codex|hexo|git|github actions|github|docker|maven|gradle)\b"),
}

SAMPLE_CONFIG = {
    "source": {"type": "current-session", "path": None, "session_key": None, "base_dir": "."},
    "content_profile": {
        "include_system_env": True,
        "include_dev_env": True,
        "include_commands": True,
        "include_file_changes": True,
        "include_failed_attempts": True,
        "include_timeline": False,
        "include_raw_logs": False,
        "max_message_chars": 4000,
    },
    "style_profile": {
        "tone": "简洁、直接、偏实战",
        "perspective": "first-person",
        "language": "zh-CN",
        "verbosity": "medium",
        "intro_style": "problem-first",
        "section_order": [
            "background",
            "symptoms",
            "investigation",
            "root_cause",
            "fix",
            "environment",
            "files",
            "commands",
            "lesson",
        ],
    },
    "renderer": {
        "type": "hexo",
        "post_dir": "source/_posts",
        "slug_pattern": "{date}-{slug}",
        "default_categories": ["AI开发", "Agent实践"],
        "default_tags": ["agent-blogger"],
        "front_matter": {"author": "hl128k", "comments": True, "toc": True},
    },
    "workflow": {
        "mode": "review",
    },
    "publish": {
        "enabled": False,
        "mode": "git",
        "git": {
            "repo_dir": "/path/to/blog",
            "remote": "origin",
            "branch": "main",
            "commit": True,
            "push": True,
            "commit_message": "chore(blog): publish {title}",
        },
        "github_api": {
            "repo": "owner/repo",
            "branch": "main",
            "path_template": "source/_posts/{filename}",
            "token_env": "GITHUB_TOKEN",
            "commit_message": "chore(blog): publish {title}",
        },
    },
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


def add_publish_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--publish", action="store_true", help="Publish after writing Markdown, overriding publish.enabled=false")
    group.add_argument("--no-publish", action="store_true", help="Do not publish, overriding publish.enabled=true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reduce agent transcripts into blog-ready Hexo Markdown.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init-config", help="Write a sample config file")
    p_init.add_argument("--output", default="agent-blogger.config.yaml")

    p_inspect = subparsers.add_parser("inspect", help="Inspect a transcript source")
    p_inspect.add_argument("input", nargs="?")
    p_inspect.add_argument("--source-path")
    p_inspect.add_argument("--source", default="auto")
    p_inspect.add_argument("--session-key")
    p_inspect.add_argument("--base-dir")
    p_inspect.add_argument("--config")

    p_reduce = subparsers.add_parser("reduce", help="Reduce transcript into IssueContext JSON")
    p_reduce.add_argument("input", nargs="?")
    p_reduce.add_argument("--source-path")
    p_reduce.add_argument("--source", default="auto")
    p_reduce.add_argument("--session-key")
    p_reduce.add_argument("--base-dir")
    p_reduce.add_argument("--config")
    p_reduce.add_argument("--output")

    p_render = subparsers.add_parser("render-hexo", help="Render IssueContext JSON into Hexo Markdown")
    p_render.add_argument("input", help="Path to IssueContext JSON")
    p_render.add_argument("--config")
    p_render.add_argument("--output")
    add_publish_flags(p_render)

    p_pipeline = subparsers.add_parser("pipeline", help="Run transcript -> IssueContext -> Hexo Markdown")
    p_pipeline.add_argument("input", nargs="?")
    p_pipeline.add_argument("--source-path")
    p_pipeline.add_argument("--source", default="auto")
    p_pipeline.add_argument("--session-key")
    p_pipeline.add_argument("--base-dir")
    p_pipeline.add_argument("--config")
    p_pipeline.add_argument("--output")
    add_publish_flags(p_pipeline)

    return parser.parse_args()


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return json.loads(json.dumps(SAMPLE_CONFIG))
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML config files")
        data = yaml.safe_load(text) or {}
    elif suffix == ".json":
        data = json.loads(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            if yaml is None:
                raise RuntimeError("PyYAML is required to read non-JSON config files")
            data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise TypeError("config root must be a mapping")
    return data


def write_config(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    if yaml is None:
        raise RuntimeError("PyYAML is required to write YAML config files")
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False), encoding="utf-8")


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_source_path(path_str: str, base_dir: str | None = None) -> Path:
    path = Path(path_str)
    if path.is_absolute() or not base_dir:
        return path
    return Path(base_dir).expanduser() / path


def resolve_source_options(args: argparse.Namespace, config: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    source_config = config.get("source", {}) or {}
    if not isinstance(source_config, dict):
        raise TypeError("source config must be a mapping")

    cli_path = getattr(args, "source_path", None) or getattr(args, "input", None)
    config_path = source_config.get("path")
    path = cli_path or config_path

    cli_source = getattr(args, "source", None)
    if cli_source and cli_source != "auto":
        source = cli_source
    elif cli_path:
        source = "auto"
    else:
        source = str(source_config.get("type") or "current-session")

    cli_base_dir = getattr(args, "base_dir", None)
    base_dir = cli_base_dir if cli_base_dir is not None else (None if cli_path else source_config.get("base_dir"))
    session_key = getattr(args, "session_key", None) or source_config.get("session_key")

    if not path:
        if source in {"current-session", "openclaw-current-session", "openclaw-session", "openclaw-session-history"}:
            raise ValueError("current OpenClaw session input must be collected by the host agent; for CLI runs provide INPUT, --source-path, or source.path")
        raise ValueError("missing transcript input; provide INPUT, --source-path, or source.path")
    return str(path), source, str(base_dir) if base_dir else None, str(session_key) if session_key else None


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


def parse_jsonl(path: Path, source_name: str) -> SessionSnapshot:
    messages: list[Message] = []
    metadata: dict[str, Any] = {"path": str(path)}
    session_id = path.stem
    title = None

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            messages.append(Message(role="assistant", text=line))
            continue

        if title is None:
            title = entry.get("title") or entry.get("sessionTitle") or title
        if "cwd" in entry and "cwd" not in metadata:
            metadata["cwd"] = entry["cwd"]
        if "model" in entry and "model" not in metadata:
            metadata["model"] = entry["model"]

        text = extract_message_text(entry)
        if not text:
            continue
        messages.append(
            Message(
                role=detect_role(entry),
                text=text,
                timestamp=entry.get("timestamp") or entry.get("created_at") or entry.get("time"),
            )
        )

    snapshot = SessionSnapshot(source=source_name, session_id=session_id, title=title, metadata=metadata, messages=messages)
    enrich_snapshot(snapshot)
    return snapshot


def parse_json(path: Path, source_name: str) -> SessionSnapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, Any] = {"path": str(path)}
    session_id = path.stem
    title = None
    messages: list[Message] = []

    if isinstance(data, list):
        iterable = data
    elif isinstance(data, dict):
        title = data.get("title") or data.get("sessionTitle") or data.get("name")
        session_id = str(data.get("session_id") or data.get("id") or session_id)
        for key in ("repo", "cwd", "model", "agent", "source"):
            if key in data:
                metadata[key] = data[key]
        iterable = data.get("messages") or data.get("conversation") or data.get("items") or []
    else:
        iterable = []

    for item in iterable:
        if isinstance(item, str):
            messages.append(Message(role="assistant", text=item))
            continue
        if not isinstance(item, dict):
            continue
        text = extract_message_text(item)
        if not text:
            continue
        messages.append(
            Message(
                role=detect_role(item),
                text=text,
                timestamp=item.get("timestamp") or item.get("created_at") or item.get("time"),
            )
        )

    snapshot = SessionSnapshot(source=source_name, session_id=session_id, title=title, metadata=metadata, messages=messages)
    enrich_snapshot(snapshot)
    return snapshot


def parse_markdown_like(path: Path, source_name: str) -> SessionSnapshot:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    messages: list[Message] = []
    current_role = "assistant"
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        if text:
            messages.append(Message(role=current_role, text=text))
        buffer = []

    for line in lines:
        role_match = re.match(r"^(?:###\s*)?(User|Assistant|System|Tool)\s*:?$", line.strip(), re.IGNORECASE)
        prefix_match = re.match(r"^(User|Assistant|System|Tool)\s*:\s*(.*)$", line.strip(), re.IGNORECASE)
        if role_match:
            flush()
            current_role = ROLE_HINTS[role_match.group(1).lower()]
            continue
        if prefix_match:
            flush()
            current_role = ROLE_HINTS[prefix_match.group(1).lower()]
            remainder = prefix_match.group(2).strip()
            if remainder:
                buffer.append(remainder)
            continue
        buffer.append(line)
    flush()

    snapshot = SessionSnapshot(source=source_name, session_id=path.stem, title=None, metadata={"path": str(path)}, messages=messages)
    enrich_snapshot(snapshot)
    return snapshot


def load_snapshot(path_str: str, source: str = "auto", base_dir: str | None = None, session_key: str | None = None) -> SessionSnapshot:
    path = resolve_source_path(path_str, base_dir)
    if not path.exists():
        raise FileNotFoundError(f"input not found: {path}")

    if source == "auto":
        if path.suffix.lower() == ".jsonl":
            source = "codex-jsonl"
        elif path.suffix.lower() == ".json":
            source = "generic-json"
        else:
            source = "markdown-transcript"

    if path.suffix.lower() == ".jsonl":
        snapshot = parse_jsonl(path, source)
    elif path.suffix.lower() == ".json":
        snapshot = parse_json(path, source)
    else:
        snapshot = parse_markdown_like(path, source)

    if base_dir:
        snapshot.metadata.setdefault("base_dir", str(Path(base_dir).expanduser()))
    if session_key:
        snapshot.metadata["session_key"] = session_key
    return snapshot


def enrich_snapshot(snapshot: SessionSnapshot) -> None:
    all_text = "\n\n".join(message.text for message in snapshot.messages if message.text)
    snapshot.commands = extract_commands(all_text)
    snapshot.files = extract_files(all_text)
    snapshot.errors = extract_errors(all_text)
    snapshot.environment = extract_environment(all_text)


def extract_commands(text: str) -> list[str]:
    commands: list[str] = []

    for block in CODE_FENCE_RE.findall(text):
        for line in block.splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                commands.append(cleaned)

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("$ "):
            commands.append(stripped[2:].strip())

    for match in INLINE_COMMAND_RE.finditer(text):
        commands.append(match.group(1).strip())

    return dedupe_keep_order(commands)[:20]


def extract_files(text: str) -> list[str]:
    return dedupe_keep_order(match.group(0) for match in FILE_RE.finditer(text))[:20]


def extract_errors(text: str) -> list[str]:
    candidates = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and ERROR_LINE_RE.search(stripped):
            candidates.append(stripped[:300])
    return dedupe_keep_order(candidates)[:15]


def extract_environment(text: str) -> dict[str, list[str]]:
    env: dict[str, list[str]] = {}
    for key, pattern in ENV_PATTERNS.items():
        matches = dedupe_keep_order(match.group(0) for match in pattern.finditer(text))
        if matches:
            env[key] = matches[:10]
    return env


def clamp_messages(messages: list[Message], max_chars: int) -> list[Message]:
    if max_chars <= 0:
        return messages
    result = []
    for message in messages:
        text = message.text
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + " …[truncated]"
        result.append(Message(role=message.role, text=text, timestamp=message.timestamp))
    return result


def reduce_snapshot(snapshot: SessionSnapshot, config: dict[str, Any]) -> IssueContext:
    content = config.get("content_profile", {})
    max_message_chars = int(content.get("max_message_chars", 4000))
    messages = clamp_messages(snapshot.messages, max_message_chars)
    user_messages = [m for m in messages if m.role == "user" and m.text.strip()]
    assistant_messages = [m for m in messages if m.role == "assistant" and m.text.strip()]

    topic = safe_title(snapshot.title or first_sentence(user_messages[0].text) if user_messages else snapshot.session_id or "agent session recap")

    summary_parts = []
    if user_messages:
        summary_parts.append("这次会话的起点是：" + first_sentence(user_messages[0].text, 180))
    if snapshot.errors:
        summary_parts.append("期间出现了明显的报错或失败信号。")
    if assistant_messages:
        summary_parts.append("最终收敛到一个可执行的处理方向或修复方案。")
    summary = normalize_space(" ".join(summary_parts)) or "本次会话围绕一个具体的开发/排障问题展开，并逐步收敛到可执行结论。"

    investigation_steps = build_investigation_steps(messages)
    failed_attempts = snapshot.errors[:5] if content.get("include_failed_attempts", True) else []
    fix = first_sentence(assistant_messages[-1].text, 220) if assistant_messages else "尚未自动确认"
    root_cause = infer_root_cause(snapshot, assistant_messages)
    lessons = build_lessons(snapshot, root_cause, fix)
    keywords = build_keywords(topic, snapshot)

    environment: dict[str, list[str]] = {}
    if content.get("include_system_env", True) or content.get("include_dev_env", True):
        environment = snapshot.environment

    files_changed = snapshot.files[:12] if content.get("include_file_changes", True) else []
    commands_used = snapshot.commands[:12] if content.get("include_commands", True) else []

    return IssueContext(
        topic=topic,
        summary=summary,
        symptoms=snapshot.errors[:8],
        investigation_steps=investigation_steps,
        failed_attempts=failed_attempts,
        root_cause=root_cause,
        fix=fix,
        files_changed=files_changed,
        commands_used=commands_used,
        environment=environment,
        lessons=lessons,
        keywords=keywords,
    )


def build_investigation_steps(messages: list[Message]) -> list[str]:
    steps: list[str] = []
    for message in messages:
        text = first_sentence(message.text, 180)
        if not text:
            continue
        if message.role == "user":
            steps.append("用户提出/补充：" + text)
        elif message.role == "assistant":
            steps.append("助手分析/执行：" + text)
        elif message.role == "tool":
            steps.append("工具输出：" + text)
        if len(steps) >= 8:
            break
    return dedupe_keep_order(steps)


def infer_root_cause(snapshot: SessionSnapshot, assistant_messages: list[Message]) -> str:
    combined_text = "\n".join(message.text for message in snapshot.messages)
    lowered = combined_text.lower()

    if "stdin" in lowered and "with-token" in lowered:
        return "`gh auth login --with-token` 会从 stdin 读取 token；如果直接裸跑而没有通过管道或重定向提供 token，看起来就会像卡住不动。"
    if snapshot.errors:
        return "从对话中的报错信号看，核心问题与以下线索最相关：" + snapshot.errors[-1]
    if assistant_messages:
        return "从最终回复看，问题的根因需要结合最后的分析结论进一步确认。"
    return "尚未自动确认"


def build_lessons(snapshot: SessionSnapshot, root_cause: str, fix: str) -> list[str]:
    lessons = [
        "优先把原始长对话压缩成结构化上下文，再交给模型写正文，可以明显减少 token 浪费。",
    ]
    if snapshot.files:
        lessons.append("涉及文件较多时，先提取关键文件名再写复盘，会比整段 transcript 更清晰。")
    if snapshot.errors:
        lessons.append("保留代表性的错误行比保留整段日志更有复盘价值。")
    if root_cause != "尚未自动确认" and fix != "尚未自动确认":
        lessons.append("根因和修复方案应分开写，避免把结果倒灌成原因。")
    return dedupe_keep_order(lessons)[:5]


def build_keywords(topic: str, snapshot: SessionSnapshot) -> list[str]:
    tokens = [topic]
    tokens.extend(snapshot.files[:4])
    for values in snapshot.environment.values():
        tokens.extend(values[:2])
    return dedupe_keep_order(tokens)[:8]


def issue_from_json(path: str | Path) -> IssueContext:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return IssueContext(**data)


def render_hexo(issue: IssueContext, config: dict[str, Any]) -> str:
    style = config.get("style_profile", {})
    content = config.get("content_profile", {})
    renderer = config.get("renderer", {})
    front_matter = dict(renderer.get("front_matter", {}))
    date_value = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    tags = dedupe_keep_order(list(renderer.get("default_tags", [])) + issue.keywords[:5])
    categories = dedupe_keep_order(renderer.get("default_categories", []))

    front_matter_lines = [
        "---",
        f"title: {json.dumps(issue.topic, ensure_ascii=False)}",
        f"date: {date_value}",
    ]
    if tags:
        front_matter_lines.append("tags:")
        front_matter_lines.extend(f"  - {tag}" for tag in tags)
    if categories:
        front_matter_lines.append("categories:")
        front_matter_lines.extend(f"  - {category}" for category in categories)
    for key, value in front_matter.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        front_matter_lines.append(f"{key}: {rendered}")
    front_matter_lines.append("---")

    tone = style.get("tone", "简洁、直接、偏实战")
    section_order = style.get(
        "section_order",
        ["background", "symptoms", "investigation", "root_cause", "fix", "environment", "files", "commands", "lesson"],
    )

    section_map: dict[str, str] = {
        "background": f"## 背景\n\n{issue.summary}\n\n这篇记录采用 **{tone}** 的复盘方式，重点保留问题、处理过程和最终结论。",
        "symptoms": render_bullets("## 问题现象", issue.symptoms),
        "investigation": render_bullets("## 排查过程", issue.investigation_steps),
        "root_cause": f"## 根因判断\n\n{issue.root_cause}",
        "fix": f"## 解决方案\n\n{issue.fix}",
        "environment": render_key_values("## 环境信息", issue.environment),
        "files": render_bullets("## 涉及文件", issue.files_changed),
        "commands": render_commands("## 关键命令", issue.commands_used),
        "lesson": render_bullets("## 复盘与经验", issue.lessons),
    }

    sections: list[str] = []
    for key in section_order:
        if key == "environment" and not (content.get("include_system_env", True) or content.get("include_dev_env", True)):
            continue
        if key == "commands" and not content.get("include_commands", True):
            continue
        if key == "files" and not content.get("include_file_changes", True):
            continue
        if key == "symptoms" and not issue.symptoms:
            continue
        if key == "investigation" and not issue.investigation_steps:
            continue
        if key == "environment" and not issue.environment:
            continue
        if key == "files" and not issue.files_changed:
            continue
        if key == "commands" and not issue.commands_used:
            continue
        block = section_map.get(key)
        if block:
            sections.append(block)

    return "\n".join(front_matter_lines) + "\n\n" + "\n\n".join(section for section in sections if section.strip()) + "\n"


def render_bullets(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [title, ""]
    lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def render_commands(title: str, commands: list[str]) -> str:
    if not commands:
        return ""
    body = "\n".join(commands)
    return f"{title}\n\n```sh\n{body}\n```"


def render_key_values(title: str, mapping: dict[str, list[str]]) -> str:
    if not mapping:
        return ""
    lines = [title, ""]
    for key, values in mapping.items():
        if values:
            lines.append(f"- **{key}**: {', '.join(values)}")
    return "\n".join(lines)


def default_output_path(issue: IssueContext, config: dict[str, Any], output: str | None) -> Path:
    if output:
        return Path(output)
    renderer = config.get("renderer", {})
    post_dir = Path(renderer.get("post_dir", "source/_posts"))
    slug_pattern = renderer.get("slug_pattern", "{date}-{slug}")
    date_value = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(issue.topic)
    filename = slug_pattern.format(date=date_value, slug=slug) + ".md"
    return post_dir / filename


def write_markdown(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def publish_template_vars(issue: IssueContext, output_path: Path) -> dict[str, str]:
    now = datetime.now().astimezone()
    return {
        "title": issue.topic,
        "slug": slugify(issue.topic),
        "filename": output_path.name,
        "path": str(output_path),
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_publish_template(template: str, issue: IssueContext, output_path: Path) -> str:
    return template.format(**publish_template_vars(issue, output_path))


def workflow_mode(config: dict[str, Any]) -> str:
    workflow_config = config.get("workflow", {}) or {}
    mode = workflow_config.get("mode")
    if isinstance(mode, str) and mode.strip():
        normalized = mode.strip().lower()
        if normalized not in {"draft", "review", "publish"}:
            raise ValueError(f"unsupported workflow mode: {mode}")
        return normalized

    # Backward compatibility for older configs that only had publish.enabled.
    publish_config = config.get("publish", {}) or {}
    if publish_config.get("enabled", False):
        return "publish"
    return "draft"


def should_publish(config: dict[str, Any], publish: bool = False, no_publish: bool = False) -> bool:
    if no_publish:
        return False
    if publish:
        return True
    return workflow_mode(config) == "publish"


def publish_after_write(config: dict[str, Any], issue: IssueContext, output_path: Path, publish: bool = False, no_publish: bool = False) -> None:
    if not should_publish(config, publish=publish, no_publish=no_publish):
        return

    publish_config = config.get("publish", {}) or {}
    mode = publish_config.get("mode", "git")
    if mode in {"none", "disabled", "off"}:
        return
    if mode == "git":
        publish_git(publish_config, issue, output_path)
        return
    if mode in {"github-api", "github_api"}:
        publish_github_api(publish_config, issue, output_path)
        return
    raise ValueError(f"unsupported publish mode: {mode}")


def git_config(publish_config: dict[str, Any]) -> dict[str, Any]:
    nested = publish_config.get("git")
    if isinstance(nested, dict):
        merged = dict(publish_config)
        merged.update(nested)
        return merged
    return publish_config


def resolve_git_repo_dir(git_cfg: dict[str, Any], output_path: Path) -> Path:
    configured = git_cfg.get("repo_dir")
    if configured:
        repo_dir = Path(configured).expanduser().resolve()
        if not (repo_dir / ".git").exists():
            raise FileNotFoundError(f"publish.git.repo_dir is not a git repository: {repo_dir}")
        return repo_dir

    current = output_path.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ValueError("publish.git.repo_dir is required unless output is inside a git repository")


def run_git(repo_dir: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def publish_git(publish_config: dict[str, Any], issue: IssueContext, output_path: Path) -> None:
    git_cfg = git_config(publish_config)
    repo_dir = resolve_git_repo_dir(git_cfg, output_path)
    resolved_output = output_path.resolve()
    try:
        rel_path = resolved_output.relative_to(repo_dir)
    except ValueError as exc:
        raise ValueError(f"output path must be inside publish.git.repo_dir: {resolved_output}") from exc

    run_git(repo_dir, ["add", str(rel_path)])
    status = run_git(repo_dir, ["status", "--porcelain", "--", str(rel_path)])
    if not status.stdout.strip():
        print("publish skipped: no git changes")
        return

    if git_cfg.get("commit", True):
        message_template = git_cfg.get("commit_message", "chore(blog): publish {title}")
        message = format_publish_template(message_template, issue, output_path)
        commit = run_git(repo_dir, ["commit", "-m", message, "--", str(rel_path)], check=False)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
        if commit.returncode == 0:
            print("published commit created")

    if git_cfg.get("push", True):
        remote = git_cfg.get("remote", "origin")
        branch = git_cfg.get("branch")
        refspec = f"HEAD:{branch}" if branch else "HEAD"
        run_git(repo_dir, ["push", remote, refspec])
        print(f"published git push to {remote} {refspec}")


def github_api_config(publish_config: dict[str, Any]) -> dict[str, Any]:
    nested = publish_config.get("github_api")
    if isinstance(nested, dict):
        merged = dict(publish_config)
        merged.update(nested)
        return merged
    return publish_config


def github_request(method: str, url: str, token: str, payload: dict[str, Any] | None = None, allow_404: bool = False) -> dict[str, Any] | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-blogger",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if allow_404 and exc.code == 404:
            return None
        raise RuntimeError(f"GitHub API {method} failed with HTTP {exc.code}: {body}") from exc


def publish_github_api(publish_config: dict[str, Any], issue: IssueContext, output_path: Path) -> None:
    api_cfg = github_api_config(publish_config)
    repo = api_cfg.get("repo")
    if not repo:
        raise ValueError("publish.github_api.repo is required for github-api mode")

    token_env = api_cfg.get("token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"environment variable {token_env} is required for github-api publishing")

    branch = api_cfg.get("branch", "main")
    path_template = api_cfg.get("path_template", "source/_posts/{filename}")
    repo_path = format_publish_template(path_template, issue, output_path).lstrip("/")
    encoded_path = urllib.parse.quote(repo_path, safe="/")
    base_url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"

    existing = github_request("GET", f"{base_url}?ref={urllib.parse.quote(branch)}", token, allow_404=True)
    content = output_path.read_bytes()
    payload: dict[str, Any] = {
        "message": format_publish_template(api_cfg.get("commit_message", "chore(blog): publish {title}"), issue, output_path),
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]

    github_request("PUT", base_url, token, payload=payload)
    print(f"published GitHub API commit to {repo}@{branch}:{repo_path}")


def snapshot_summary(snapshot: SessionSnapshot) -> dict[str, Any]:
    return {
        "source": snapshot.source,
        "session_id": snapshot.session_id,
        "title": snapshot.title,
        "message_count": len(snapshot.messages),
        "commands": snapshot.commands[:8],
        "files": snapshot.files[:8],
        "errors": snapshot.errors[:8],
        "environment": snapshot.environment,
        "metadata": snapshot.metadata,
    }


def main() -> int:
    args = parse_args()

    if args.command == "init-config":
        write_config(args.output, SAMPLE_CONFIG)
        print(f"wrote sample config to {args.output}")
        return 0

    if args.command == "inspect":
        config = load_config(args.config) if args.config else {}
        input_path, source, base_dir, session_key = resolve_source_options(args, config)
        snapshot = load_snapshot(input_path, source, base_dir=base_dir, session_key=session_key)
        print(json.dumps(snapshot_summary(snapshot), ensure_ascii=False, indent=2))
        return 0

    if args.command == "reduce":
        config = load_config(args.config)
        input_path, source, base_dir, session_key = resolve_source_options(args, config)
        snapshot = load_snapshot(input_path, source, base_dir=base_dir, session_key=session_key)
        issue = reduce_snapshot(snapshot, config)
        payload = asdict(issue)
        if args.output:
            write_json(args.output, payload)
            print(f"wrote issue context to {args.output}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "render-hexo":
        config = load_config(args.config)
        issue = issue_from_json(args.input)
        markdown = render_hexo(issue, config)
        output_path = default_output_path(issue, config, args.output)
        write_markdown(output_path, markdown)
        print(f"wrote hexo markdown to {output_path}")
        publish_after_write(config, issue, output_path, publish=args.publish, no_publish=args.no_publish)
        return 0

    if args.command == "pipeline":
        config = load_config(args.config)
        input_path, source, base_dir, session_key = resolve_source_options(args, config)
        snapshot = load_snapshot(input_path, source, base_dir=base_dir, session_key=session_key)
        issue = reduce_snapshot(snapshot, config)
        markdown = render_hexo(issue, config)
        output_path = default_output_path(issue, config, args.output)
        write_markdown(output_path, markdown)
        print(f"wrote hexo markdown to {output_path}")
        publish_after_write(config, issue, output_path, publish=args.publish, no_publish=args.no_publish)
        return 0

    print("unknown command", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
