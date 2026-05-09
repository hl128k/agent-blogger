#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

try:
    import yaml
except ImportError:  # pragma: no cover - optional at runtime
    yaml = None

from scripts.agent_blogger_core import IssueContext, Message, SessionSnapshot, SourceRequest
from scripts.agent_blogger_publisher import Publisher, publish_after_write, should_publish, workflow_mode
from scripts.agent_blogger_reducer import ContextReducer, derive_topic, reduce_snapshot
from scripts.agent_blogger_renderer import (
    DraftRenderer,
    default_output_path,
    issue_from_json,
    render_drafting_prompt,
    render_hexo,
    write_markdown,
)
from scripts.agent_blogger_source import (
    SourceAdapter,
    TranscriptSource,
    extract_commands,
    extract_environment,
    extract_errors,
    extract_files,
    load_snapshot,
    parse_json,
    parse_jsonl,
    parse_markdown_like,
    resolve_source_options,
    resolve_source_path,
    snapshot_summary,
)

SAMPLE_CONFIG = {
    "source": {"type": "codex-jsonl", "path": None, "session_key": None, "base_dir": "."},
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
    },
    "template_profile": {
        "type": "hexo-technical-post",
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
        "section_headings": {
            "background": "背景",
            "symptoms": "问题现象",
            "investigation": "排查过程",
            "root_cause": "根因判断",
            "fix": "解决方案",
            "environment": "环境信息",
            "files": "涉及文件",
            "commands": "关键命令",
            "lesson": "复盘与经验",
        },
        "section_templates": {
            "background": "{summary}\n\n这篇记录采用 **{tone}** 的复盘方式，重点保留问题、处理过程和最终结论。"
        },
        "optional_sections": ["environment", "files", "commands"],
    },
    "prompt_profile": {
        "system_prompt": "你是一名技术博客编辑，把结构化问题上下文整理成清晰、真实、可复盘的技术文章。不要编造不存在的环境、命令或结论。",
        "draft_prompt_template": "请根据下面的 IssueContext 写一篇 {language} 技术博客。语气：{tone}。视角：{perspective}。模板：{template_type}。章节顺序：{section_order}。",
        "include_reduced_context": True,
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

    p_prompt = subparsers.add_parser("render-prompt", help="Render a drafting prompt from IssueContext JSON and config")
    p_prompt.add_argument("input", help="Path to IssueContext JSON")
    p_prompt.add_argument("--config")
    p_prompt.add_argument("--output")

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


def write_text_file(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()

    if args.command == "init-config":
        write_config(args.output, SAMPLE_CONFIG)
        print(f"wrote sample config to {args.output}")
        return 0

    if args.command == "inspect":
        config = load_config(args.config) if args.config else {}
        request = resolve_source_options(args, config)
        snapshot = load_snapshot(request)
        print(json.dumps(snapshot_summary(snapshot), ensure_ascii=False, indent=2))
        return 0

    if args.command == "reduce":
        config = load_config(args.config)
        request = resolve_source_options(args, config)
        snapshot = load_snapshot(request)
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

    if args.command == "render-prompt":
        config = load_config(args.config)
        issue = issue_from_json(args.input)
        prompt = render_drafting_prompt(issue, config)
        if args.output:
            write_text_file(args.output, prompt)
            print(f"wrote drafting prompt to {args.output}")
        else:
            print(prompt, end="")
        return 0

    if args.command == "pipeline":
        config = load_config(args.config)
        request = resolve_source_options(args, config)
        snapshot = load_snapshot(request)
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
