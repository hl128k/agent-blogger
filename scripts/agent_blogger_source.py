from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from scripts.agent_blogger_core import (
    CODE_FENCE_RE,
    ENV_PATTERNS,
    ERROR_LINE_RE,
    FILE_RE,
    HOST_SOURCE_ALIASES,
    INLINE_COMMAND_RE,
    Message,
    SessionSnapshot,
    SourceRequest,
    dedupe_keep_order,
    detect_role,
    extract_message_text,
    normalize_space,
    text_from_any,
)


@runtime_checkable
class SourceAdapter(Protocol):
    def load(self, request: SourceRequest) -> SessionSnapshot:
        ...


class TranscriptSource:
    def load(self, request: SourceRequest) -> SessionSnapshot:
        if not request.path:
            raise ValueError("file transcript adapter requires a path")

        path = resolve_source_path(request.path, request.base_dir)
        if not path.exists():
            raise FileNotFoundError(f"input not found: {path}")

        source = request.source
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
        return snapshot


class HostSessionAdapter:
    def load(self, _request: SourceRequest) -> SessionSnapshot:
        raise ValueError(
            "current OpenClaw session input must be materialized by the host agent; "
            "for CLI runs provide INPUT, --source-path, or source.path"
        )


TranscriptFileAdapter = TranscriptSource

FILE_SOURCE_ADAPTER = TranscriptSource()
HOST_SESSION_ADAPTER = HostSessionAdapter()


def resolve_source_path(path_str: str, base_dir: str | None = None) -> Path:
    path = Path(path_str)
    if path.is_absolute() or not base_dir:
        return path
    return Path(base_dir).expanduser() / path


def resolve_source_options(args: argparse.Namespace, config: dict[str, Any]) -> SourceRequest:
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
    base_dir = cli_base_dir if cli_base_dir is not None else source_config.get("base_dir")
    session_key = getattr(args, "session_key", None) or source_config.get("session_key")

    if not path and source not in HOST_SOURCE_ALIASES:
        raise ValueError("missing transcript input; provide INPUT, --source-path, or source.path")
    return SourceRequest(
        path=str(path) if path else None,
        source=source,
        base_dir=str(base_dir) if base_dir else None,
        session_key=str(session_key) if session_key else None,
    )


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

    for match in re.finditer(r"`((?:gh|git|rg|python3?|hexo|npm|node|curl|wget|printf|export|chmod|cp|mv|rm|cat|find|read)\b[^`]+)`", text):
        commands.append(match.group(1).strip())

    deduped = dedupe_keep_order(commands)
    pruned: list[str] = []
    for index, command in enumerate(deduped):
        if any(len(other) > len(command) and other.startswith(command) for other in deduped[index + 1 :]):
            continue
        pruned.append(command)
    return pruned[:20]


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


def enrich_snapshot(snapshot: SessionSnapshot) -> None:
    all_text = "\n\n".join(message.text for message in snapshot.messages if message.text)
    snapshot.commands = extract_commands(all_text)
    snapshot.files = extract_files(all_text)
    snapshot.errors = extract_errors(all_text)
    snapshot.environment = extract_environment(all_text)


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
            current_role = detect_role({"role": role_match.group(1)})
            continue
        if prefix_match:
            flush()
            current_role = detect_role({"role": prefix_match.group(1)})
            remainder = prefix_match.group(2).strip()
            if remainder:
                buffer.append(remainder)
            continue
        buffer.append(line)
    flush()

    snapshot = SessionSnapshot(source=source_name, session_id=path.stem, title=None, metadata={"path": str(path)}, messages=messages)
    enrich_snapshot(snapshot)
    return snapshot


def load_snapshot(
    request: SourceRequest,
    source_adapter: SourceAdapter | None = None,
    host_adapter: HostSessionAdapter | None = None,
) -> SessionSnapshot:
    file_adapter = source_adapter or FILE_SOURCE_ADAPTER
    host_session_adapter = host_adapter or HOST_SESSION_ADAPTER

    if request.path:
        snapshot = file_adapter.load(request)
    else:
        if request.source not in HOST_SOURCE_ALIASES:
            raise ValueError("missing transcript input; provide INPUT, --source-path, or source.path")
        snapshot = host_session_adapter.load(request)

    if request.base_dir:
        snapshot.metadata.setdefault("base_dir", str(Path(request.base_dir).expanduser()))
    if request.session_key:
        snapshot.metadata["session_key"] = request.session_key
    return snapshot


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
