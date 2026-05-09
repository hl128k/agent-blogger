from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from scripts.agent_blogger_core import (
    DEFAULT_SECTION_HEADINGS,
    DEFAULT_SECTION_ORDER,
    IssueContext,
    dedupe_keep_order,
    safe_format_template,
    slugify,
)


@runtime_checkable
class DraftRenderer(Protocol):
    def render_drafting_prompt(self, issue: IssueContext, config: dict[str, Any]) -> str:
        ...

    def render_hexo(self, issue: IssueContext, config: dict[str, Any]) -> str:
        ...


def issue_from_json(path: str | Path) -> IssueContext:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return IssueContext(**data)


def mapping_config(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {}) or {}
    if not isinstance(value, dict):
        raise TypeError(f"{key} config must be a mapping")
    return value


def configured_section_order(config: dict[str, Any]) -> list[str]:
    template = mapping_config(config, "template_profile")
    style = mapping_config(config, "style_profile")
    raw = template.get("section_order") or template.get("include_sections") or style.get("section_order") or DEFAULT_SECTION_ORDER
    if not isinstance(raw, list):
        raise TypeError("template_profile.section_order must be a list")
    return [str(item) for item in raw if str(item).strip()]


def section_heading(config: dict[str, Any], key: str) -> str:
    template = mapping_config(config, "template_profile")
    headings = template.get("section_headings", {}) or {}
    if not isinstance(headings, dict):
        raise TypeError("template_profile.section_headings must be a mapping")
    return str(headings.get(key) or DEFAULT_SECTION_HEADINGS.get(key) or key.replace("_", " ").title())


def markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def markdown_commands(commands: list[str]) -> str:
    if not commands:
        return ""
    return "```sh\n" + "\n".join(commands) + "\n```"


def markdown_key_values(mapping: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for key, values in mapping.items():
        if values:
            lines.append(f"- **{key}**: {', '.join(values)}")
    return "\n".join(lines)


def template_vars(issue: IssueContext, config: dict[str, Any]) -> dict[str, str]:
    style = mapping_config(config, "style_profile")
    template = mapping_config(config, "template_profile")
    return {
        "title": issue.topic,
        "topic": issue.topic,
        "summary": issue.summary,
        "symptoms": markdown_list(issue.symptoms),
        "investigation": markdown_list(issue.investigation_steps),
        "failed_attempts": markdown_list(issue.failed_attempts),
        "root_cause": issue.root_cause,
        "fix": issue.fix,
        "environment": markdown_key_values(issue.environment),
        "files": markdown_list(issue.files_changed),
        "commands": markdown_commands(issue.commands_used),
        "lesson": markdown_list(issue.lessons),
        "lessons": markdown_list(issue.lessons),
        "keywords": ", ".join(issue.keywords),
        "tone": str(style.get("tone", "简洁、直接、偏实战")),
        "language": str(style.get("language", "zh-CN")),
        "perspective": str(style.get("perspective", "first-person")),
        "verbosity": str(style.get("verbosity", "medium")),
        "intro_style": str(style.get("intro_style", "problem-first")),
        "template_type": str(template.get("type", "hexo-technical-post")),
        "section_order": ", ".join(configured_section_order(config)),
        "issue_json": json.dumps(asdict(issue), ensure_ascii=False, indent=2),
    }


def render_section_with_heading(config: dict[str, Any], key: str, body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return f"## {section_heading(config, key)}\n\n{body}"


def section_templates(config: dict[str, Any]) -> dict[str, str]:
    template = mapping_config(config, "template_profile")
    raw = template.get("section_templates", {}) or {}
    if not isinstance(raw, dict):
        raise TypeError("template_profile.section_templates must be a mapping")
    return {str(key): str(value) for key, value in raw.items()}


def render_drafting_prompt(issue: IssueContext, config: dict[str, Any]) -> str:
    prompt = mapping_config(config, "prompt_profile")
    values = template_vars(issue, config)
    system_prompt = str(
        prompt.get(
            "system_prompt",
            "你是一名技术博客编辑，把结构化问题上下文整理成清晰、真实、可复盘的技术文章。不要编造不存在的环境、命令或结论。",
        )
    )
    draft_template = str(
        prompt.get(
            "draft_prompt_template",
            "请根据下面的 IssueContext 写一篇 {language} 技术博客。语气：{tone}。视角：{perspective}。模板：{template_type}。章节顺序：{section_order}。",
        )
    )
    rendered = ["# System Prompt", "", safe_format_template(system_prompt, values).strip(), "", "# Draft Prompt", "", safe_format_template(draft_template, values).strip()]
    if prompt.get("include_reduced_context", True):
        rendered.extend(["", "# Reduced IssueContext", "", "```json", values["issue_json"], "```"])
    return "\n".join(rendered).rstrip() + "\n"


def render_hexo(issue: IssueContext, config: dict[str, Any]) -> str:
    content = mapping_config(config, "content_profile")
    renderer = mapping_config(config, "renderer")
    template = mapping_config(config, "template_profile")
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

    section_order = configured_section_order(config)
    section_templates_map = section_templates(config)
    values = template_vars(issue, config)
    background_template = section_templates_map.get(
        "background",
        "{summary}\n\n这篇记录采用 **{tone}** 的复盘方式，重点保留问题、处理过程和最终结论。",
    )

    section_map: dict[str, str] = {
        "background": render_section_with_heading(config, "background", safe_format_template(background_template, values)),
        "symptoms": render_section_with_heading(config, "symptoms", markdown_list(issue.symptoms)),
        "investigation": render_section_with_heading(config, "investigation", markdown_list(issue.investigation_steps)),
        "root_cause": render_section_with_heading(config, "root_cause", issue.root_cause),
        "fix": render_section_with_heading(config, "fix", issue.fix),
        "environment": render_section_with_heading(config, "environment", markdown_key_values(issue.environment)),
        "files": render_section_with_heading(config, "files", markdown_list(issue.files_changed)),
        "commands": render_section_with_heading(config, "commands", markdown_commands(issue.commands_used)),
        "lesson": render_section_with_heading(config, "lesson", markdown_list(issue.lessons)),
    }

    sections: list[str] = []
    optional_sections = set(template.get("optional_sections", ["environment", "files", "commands"]) or [])
    if not isinstance(optional_sections, set):
        optional_sections = set(optional_sections)
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
        if key == "environment" and not issue.environment and key in optional_sections:
            continue
        if key == "files" and not issue.files_changed and key in optional_sections:
            continue
        if key == "commands" and not issue.commands_used and key in optional_sections:
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


class DefaultDraftRenderer:
    def render_drafting_prompt(self, issue: IssueContext, config: dict[str, Any]) -> str:
        return render_drafting_prompt(issue, config)

    def render_hexo(self, issue: IssueContext, config: dict[str, Any]) -> str:
        return render_hexo(issue, config)


DEFAULT_DRAFT_RENDERER = DefaultDraftRenderer()
