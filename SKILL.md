---
name: agent-blogger
description: Turn coding-agent conversations and transcripts into structured blog-ready drafts, especially for OpenClaw sessions, Codex JSONL transcripts, and similar agent logs. Use when the user wants to summarize a debugging session, implementation session, refactor, incident, or architecture discussion into a post; generate Hexo-compatible Markdown with configurable tags/categories/front matter; optionally push the rendered post to a blog repo via git or GitHub API; or extract issue context without dumping an entire raw transcript into the model context.
---

# Agent Blogger

## Overview

Use this skill to transform agent conversations into publishable technical writing.

Prefer a **local reduction pipeline** over copying large raw transcripts into the model context:

1. collect only the relevant transcript or session slice
2. normalize it into a compact session snapshot
3. reduce it into issue/context facts locally
4. draft the article from the reduced context
5. render the result as Hexo Markdown

This skill is designed to keep token usage low while preserving the useful parts of the session: problem statement, symptoms, failed attempts, root cause, fix, files touched, commands used, and lessons learned.

## V1 Scope

Treat this repository's first version as intentionally narrow:

- **Sources**: OpenClaw session history and Codex transcript files first
- **Output**: Hexo Markdown first
- **Configuration**: YAML-first source config + content profile + style profile + prompt profile + template profile + renderer config + optional publish config
- **Architecture**: light interfaces, no heavy plugin framework

Keep publishing explicit and opt-in: generate the post first, then optionally push it through a small number of backends.

## Workflow

### 1. Choose the source path

Use one of these paths:

- **OpenClaw current/recent session**: use session tools to gather the bounded history you need, then reduce it before drafting
- **Codex transcript file**: parse JSONL/JSON/Markdown transcript files locally; use an explicit path such as `transcripts/codex-session.jsonl`
- **Other sources**: only if they can be normalized into the same snapshot shape

Source values:

- file mode values: `auto`, `codex-jsonl`, `generic-json`, `markdown-transcript`
- host materialized-session values: `current-session`, `openclaw-current-session`, `openclaw-session`, `openclaw-session-history`

Resolution precedence:

```text
CLI --source-path or positional INPUT > config source.path > host current session
CLI --source > config source.type > current-session
CLI --session-key > config source.session_key
CLI --base-dir > config source.base_dir
```

Semantics:

- `base_dir only resolves relative transcript file paths`
- `session_key is host session identity/metadata and does not participate in local path lookup`

When the source is very large, prefer a targeted slice (specific time range, issue window, or message range) instead of the full history.

### 2. Normalize before reasoning

Normalize raw transcript material into a compact structure with these concepts:

- session metadata
- ordered messages
- extracted commands
- extracted file paths
- extracted error lines
- optional environment hints

Use `references/architecture.md` for the target data model.

### 3. Reduce locally

Before asking the model to draft prose, reduce the transcript into a compact issue context:

- what was the original goal
- what symptoms appeared
- what investigations happened
- which attempts failed
- what finally fixed it
- what files/commands/environment matter

If the user only wants a post skeleton, the local reducer output alone may be enough.

### 4. Apply writing configuration

Keep **content selection**, **prompting**, **template shape**, and **rendering** separate:

- content profile decides what facts are collected
- style profile decides how the post sounds
- prompt profile decides how the reduced context is turned into prose instructions
- template profile decides section order, headings, and reusable section text
- renderer decides the final output format

Use `references/configuration.md` for the current YAML-first config layout, example values, and JSON compatibility notes.

### 5. Render Hexo output

For Hexo output, produce:

- front matter
- title
- tags/categories
- body sections in a stable order

Write the generated file into the target Hexo repo's `source/_posts/` directory only after the content looks correct.

### 6. Optionally publish

Use `workflow.mode` to control the default behavior:

- `draft`: stop after writing Markdown
- `review`: stop after writing Markdown unless explicitly published
- `publish`: push automatically after generation

If publishing is enabled, push the rendered Markdown after generation:

- `git`: local repo commit/push
- `github-api`: GitHub Contents API using a token from environment

Do not store raw secrets in the config file.

## Practical Rules

- Prefer smaller, issue-focused inputs over full-session dumps.
- Keep extraction deterministic where possible.
- Do not assume every conversation deserves a blog post; skip or narrow scope when the material is thin.
- When environment details are absent, omit them rather than inventing them.
- When root cause is uncertain, say so explicitly in the draft instead of overstating confidence.

## Resources

### `scripts/agent_blogger.py`
Single-file CLI for transcript inspection, reduction, sample config generation, and Hexo Markdown rendering.

### `references/architecture.md`
V1 layering, extension points, data model, and token-saving design notes.

### `references/configuration.md`
Config schema, YAML example, and mapping between content/style/prompt/template/renderer/publish knobs.
