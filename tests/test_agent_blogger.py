from argparse import Namespace
import json
import tempfile
import unittest
from pathlib import Path

from scripts.agent_blogger import (
    Message,
    SessionSnapshot,
    SourceRequest,
    SAMPLE_CONFIG,
    derive_topic,
    extract_commands,
    extract_environment,
    extract_errors,
    extract_files,
    load_config,
    load_snapshot,
    parse_jsonl,
    parse_markdown_like,
    resolve_source_options,
    reduce_snapshot,
    render_drafting_prompt,
    render_hexo,
    should_publish,
    workflow_mode,
)


def sample_config() -> dict:
    return {
        "content_profile": {
            "include_system_env": True,
            "include_dev_env": True,
            "include_commands": True,
            "include_file_changes": True,
            "include_failed_attempts": True,
            "max_message_chars": 4000,
        },
        "style_profile": {
            "tone": "简洁、直接、偏实战",
            "perspective": "first-person",
            "language": "zh-CN",
            "verbosity": "medium",
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
            "optional_sections": ["environment", "files", "commands"],
        },
        "prompt_profile": {
            "system_prompt": "你是一名技术博客编辑。",
            "draft_prompt_template": "请根据下面的 IssueContext 写一篇 {language} 技术博客。",
            "include_reduced_context": True,
        },
        "renderer": {
            "type": "hexo",
            "post_dir": "source/_posts",
            "slug_pattern": "{date}-{slug}",
            "default_categories": ["AI开发", "Agent实践"],
            "default_tags": ["agent-blogger"],
            "front_matter": {"author": "hl128k", "toc": True},
        },
        "workflow": {"mode": "review"},
    }


class AgentBloggerTests(unittest.TestCase):
    def test_extract_helpers_find_key_context(self) -> None:
        text = """
        Need to debug Hexo on Ubuntu 24.04 with Python 3.12.

        ```sh
        python3 scripts/agent_blogger.py reduce sample.jsonl --config agent-blogger.config.yaml
        ```

        Run `git status --short` before publishing.
        ERROR: permission denied while writing source/_posts/example.md
        """

        commands = extract_commands(text)
        files = extract_files(text)
        errors = extract_errors(text)
        environment = extract_environment(text)

        self.assertIn(
            "python3 scripts/agent_blogger.py reduce sample.jsonl --config agent-blogger.config.yaml",
            commands,
        )
        self.assertIn("git status --short", commands)
        self.assertIn("scripts/agent_blogger.py", files)
        self.assertIn("sample.jsonl", files)
        self.assertIn("source/_posts/example.md", files)
        self.assertEqual(errors, ["ERROR: permission denied while writing source/_posts/example.md"])
        self.assertIn("Ubuntu", environment["os"])
        self.assertIn("Python 3.12", environment["runtime"])

    def test_parse_jsonl_reduce_and_render_hexo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "session.jsonl"
            entries = [
                {
                    "title": "Fix Hexo draft pipeline",
                    "role": "user",
                    "text": "Need to turn Codex session logs into Hexo posts on Ubuntu 24.04 with Python 3.12.",
                },
                {
                    "role": "assistant",
                    "text": "Run:\n```sh\npython3 scripts/agent_blogger.py reduce session.jsonl --config agent-blogger.config.yaml\n```",
                },
                {"role": "tool", "text": "Traceback (most recent call last):\nPermission denied"},
                {
                    "role": "assistant",
                    "text": "The fix is to keep publishing optional and render the draft before pushing.",
                },
            ]
            transcript.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries), encoding="utf-8")

            snapshot = parse_jsonl(transcript, "codex-jsonl")
            issue = reduce_snapshot(snapshot, sample_config())
            markdown = render_hexo(issue, sample_config())

        self.assertEqual(snapshot.title, "Fix Hexo draft pipeline")
        self.assertEqual(issue.topic, "Fix Hexo draft pipeline")
        self.assertIn("Permission denied", "\n".join(issue.symptoms))
        self.assertIn("Ubuntu", issue.environment["os"])
        self.assertIn("Python 3.12", issue.environment["runtime"])
        self.assertTrue(any("scripts/agent_blogger.py" in item for item in issue.files_changed))
        self.assertTrue(any("python3 scripts/agent_blogger.py reduce" in item for item in issue.commands_used))
        self.assertIn('title: "Fix Hexo draft pipeline"', markdown)
        self.assertIn("## 背景", markdown)
        self.assertIn("## 问题现象", markdown)
        self.assertIn("## 关键命令", markdown)
        self.assertIn("tags:", markdown)
        self.assertIn("agent-blogger", markdown)

    def test_markdown_like_transcript_parser_splits_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "session.md"
            transcript.write_text(
                "User: Please inspect scripts/agent_blogger.py\n"
                "Assistant: $ python3 scripts/agent_blogger.py --help\n"
                "Tool:\n"
                "usage: agent_blogger.py ...\n",
                encoding="utf-8",
            )

            snapshot = parse_markdown_like(transcript, "markdown-transcript")

        self.assertEqual([message.role for message in snapshot.messages], ["user", "assistant", "tool"])
        self.assertIn("scripts/agent_blogger.py", snapshot.files)
        self.assertTrue(any(command.startswith("python3 scripts/agent_blogger.py") for command in snapshot.commands))

    def test_render_drafting_prompt_keeps_reduced_context(self) -> None:
        snapshot = SessionSnapshot(
            source="markdown-transcript",
            session_id="example",
            messages=[
                Message(role="user", text="Need a blog draft from this debugging session."),
                Message(role="assistant", text="The fix is to render a prompt from IssueContext first."),
            ],
        )
        issue = reduce_snapshot(snapshot, sample_config())
        prompt = render_drafting_prompt(issue, sample_config())

        self.assertIn("# System Prompt", prompt)
        self.assertIn("# Reduced IssueContext", prompt)
        self.assertIn('"topic"', prompt)
        self.assertIn(issue.topic, prompt)

    def test_topic_and_workflow_fallbacks_are_explicit(self) -> None:
        snapshot = SessionSnapshot(source="codex-jsonl", session_id="session-123")

        self.assertEqual(derive_topic(snapshot, []), "session-123")
        self.assertEqual(workflow_mode({"workflow": {"mode": "publish"}}), "publish")
        self.assertTrue(should_publish({"workflow": {"mode": "draft"}}, publish=True))
        self.assertFalse(should_publish({"workflow": {"mode": "publish"}}, no_publish=True))

    def test_example_config_exists_and_loads(self) -> None:
        example_path = Path(__file__).resolve().parents[1] / "agent-blogger.config.example.yaml"
        config = load_config(str(example_path))

        self.assertTrue(example_path.exists())
        self.assertEqual(config["workflow"]["mode"], "review")
        self.assertEqual(config["renderer"]["post_dir"], "source/_posts")
        self.assertIn("agent-blogger", config["renderer"]["default_tags"])
        self.assertEqual(
            config["source"],
            {"type": "codex-jsonl", "path": None, "session_key": None, "base_dir": "."},
        )

    def test_sample_config_source_defaults_match_example(self) -> None:
        self.assertEqual(
            SAMPLE_CONFIG["source"],
            {"type": "codex-jsonl", "path": None, "session_key": None, "base_dir": "."},
        )

    def test_resolve_source_options_respects_cli_priority(self) -> None:
        args = Namespace(
            input="cli/session.jsonl",
            source_path=None,
            source="auto",
            session_key="cli-session",
            base_dir="cli-base",
        )
        config = {
            "source": {
                "type": "current-session",
                "path": "config/session.jsonl",
                "session_key": "config-session",
                "base_dir": "config-base",
            }
        }

        request = resolve_source_options(args, config)

        self.assertEqual(request.path, "cli/session.jsonl")
        self.assertEqual(request.source, "auto")
        self.assertEqual(request.session_key, "cli-session")
        self.assertEqual(request.base_dir, "cli-base")

    def test_cli_path_uses_config_base_dir_when_not_overridden(self) -> None:
        args = Namespace(
            input="cli/session.jsonl",
            source_path=None,
            source=None,
            session_key=None,
            base_dir=None,
        )
        config = {
            "source": {
                "type": "codex-jsonl",
                "path": "config/session.jsonl",
                "session_key": None,
                "base_dir": "config-base",
            }
        }

        request = resolve_source_options(args, config)

        self.assertEqual(request.path, "cli/session.jsonl")
        self.assertEqual(request.source, "auto")
        self.assertEqual(request.base_dir, "config-base")

    def test_resolve_source_options_prefers_config_path_before_host_session(self) -> None:
        args = Namespace(
            input=None,
            source_path=None,
            source=None,
            session_key=None,
            base_dir=None,
        )
        config = {
            "source": {
                "type": "current-session",
                "path": "config/session.jsonl",
                "session_key": "config-session",
                "base_dir": "config-base",
            }
        }

        request = resolve_source_options(args, config)

        self.assertEqual(request.path, "config/session.jsonl")
        self.assertEqual(request.source, "current-session")
        self.assertEqual(request.session_key, "config-session")
        self.assertEqual(request.base_dir, "config-base")

    def test_host_session_source_can_flow_through_request(self) -> None:
        args = Namespace(
            input=None,
            source_path=None,
            source="current-session",
            session_key=None,
            base_dir=None,
        )
        config = {
            "source": {
                "type": "current-session",
                "path": None,
                "session_key": "session-abc",
                "base_dir": ".",
            }
        }

        request = resolve_source_options(args, config)

        self.assertIsInstance(request, SourceRequest)
        self.assertIsNone(request.path)
        self.assertEqual(request.source, "current-session")
        self.assertEqual(request.session_key, "session-abc")
        with self.assertRaisesRegex(ValueError, "materialized"):
            load_snapshot(request)

    def test_file_mode_relative_path_uses_base_dir_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            nested_dir = base_dir / "nested"
            nested_dir.mkdir()
            transcript = nested_dir / "session.jsonl"
            expected_path = transcript.resolve()
            expected_base_dir = base_dir.resolve()
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"role": "user", "text": "Need to inspect a codex transcript file."}, ensure_ascii=False),
                        json.dumps({"role": "assistant", "text": "Use a relative source.path with base_dir."}, ensure_ascii=False),
                    ]
                ),
                encoding="utf-8",
            )

            args = Namespace(
                input=None,
                source_path=None,
                source=None,
                session_key=None,
                base_dir=None,
            )
            config = {
                "source": {
                    "type": "codex-jsonl",
                    "path": "nested/session.jsonl",
                    "session_key": "session-xyz",
                    "base_dir": temp_dir,
                }
            }

            request = resolve_source_options(args, config)
            snapshot = load_snapshot(request)

        self.assertEqual(request.path, "nested/session.jsonl")
        self.assertEqual(request.source, "codex-jsonl")
        self.assertEqual(request.base_dir, temp_dir)
        self.assertEqual(snapshot.source, "codex-jsonl")
        self.assertEqual(Path(snapshot.metadata["path"]), expected_path)
        self.assertEqual(snapshot.metadata["base_dir"], str(expected_base_dir))
        self.assertEqual(snapshot.metadata["session_key"], "session-xyz")


if __name__ == "__main__":
    unittest.main()
