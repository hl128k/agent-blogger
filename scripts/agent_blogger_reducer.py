from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from scripts.agent_blogger_core import (
    FAILED_ATTEMPT_RE,
    ERROR_LINE_RE,
    FIX_RE,
    ROOT_CAUSE_RE,
    IssueContext,
    Message,
    SessionSnapshot,
    dedupe_keep_order,
    first_sentence,
    normalize_space,
    safe_title,
)


@runtime_checkable
class ContextReducer(Protocol):
    def reduce(self, snapshot: SessionSnapshot, config: dict[str, Any]) -> IssueContext:
        ...


class DefaultContextReducer:
    def reduce(self, snapshot: SessionSnapshot, config: dict[str, Any]) -> IssueContext:
        return reduce_snapshot(snapshot, config)


DEFAULT_CONTEXT_REDUCER = DefaultContextReducer()


def extract_failed_attempts(messages: list[Message], errors: list[str]) -> list[str]:
    candidates: list[str] = []

    for message in messages:
        for raw_line in message.text.splitlines():
            line = normalize_space(raw_line)
            if not line:
                continue
            if FAILED_ATTEMPT_RE.search(line) or ERROR_LINE_RE.search(line):
                candidates.append(line[:220])

    for error in errors:
        line = normalize_space(error)
        if line:
            candidates.append(line[:220])

    return dedupe_keep_order(candidates)[:8]


def extract_explicit_conclusion(messages: list[Message], pattern: re.Pattern[str], limit: int = 220) -> str:
    for message in messages:
        for raw_line in message.text.splitlines():
            line = normalize_space(raw_line)
            if not line:
                continue
            for candidate in re.split(r"(?<=[。！？.!?;；])\s+", line):
                candidate = normalize_space(candidate)
                if candidate and pattern.search(candidate):
                    return candidate[:limit].rstrip()
    return "尚未自动确认"


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


def derive_topic(snapshot: SessionSnapshot, user_messages: list[Message]) -> str:
    if snapshot.title:
        return safe_title(snapshot.title)
    if user_messages:
        return safe_title(first_sentence(user_messages[0].text))
    if snapshot.session_id:
        return safe_title(snapshot.session_id)
    return "agent session recap"


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
    explicit_root_cause = extract_explicit_conclusion(snapshot.messages, ROOT_CAUSE_RE)
    if explicit_root_cause != "尚未自动确认":
        return explicit_root_cause

    combined_text = "\n".join(message.text for message in snapshot.messages)
    lowered = combined_text.lower()

    if "stdin" in lowered and "with-token" in lowered:
        return "`gh auth login --with-token` 会从 stdin 读取 token；如果直接裸跑而没有通过管道或重定向提供 token，看起来就会像卡住不动。"
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


def reduce_snapshot(snapshot: SessionSnapshot, config: dict[str, Any]) -> IssueContext:
    content = config.get("content_profile", {})
    max_message_chars = int(content.get("max_message_chars", 4000))
    messages = clamp_messages(snapshot.messages, max_message_chars)
    user_messages = [m for m in messages if m.role == "user" and m.text.strip()]
    assistant_messages = [m for m in messages if m.role == "assistant" and m.text.strip()]

    topic = derive_topic(snapshot, user_messages)
    fix = extract_explicit_conclusion(messages, FIX_RE)
    root_cause = infer_root_cause(snapshot, assistant_messages)

    summary_parts = []
    if user_messages:
        summary_parts.append("这次会话的起点是：" + first_sentence(user_messages[0].text, 180))
    if snapshot.errors:
        summary_parts.append("期间出现了明显的报错或失败信号。")
    explicit_conclusions = [value for value in (root_cause, fix) if value != "尚未自动确认"]
    if explicit_conclusions:
        summary_parts.append("对话中明确给出的结论是：" + "；".join(explicit_conclusions))
    summary = normalize_space(" ".join(summary_parts)) or "本次会话围绕一个具体的开发/排障问题展开。"

    investigation_steps = build_investigation_steps(messages)
    failed_attempts = extract_failed_attempts(messages, snapshot.errors) if content.get("include_failed_attempts", True) else []
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
