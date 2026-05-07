---
name: agent-blogger
description: Turn coding-agent conversations and transcripts into structured blog-ready drafts, especially for OpenClaw sessions, Codex JSONL transcripts, and similar agent logs. Use when the user wants to summarize a debugging session, implementation session, refactor, incident, or architecture discussion into a post; generate Hexo-compatible Markdown with configurable tags/categories/front matter; or extract issue context without dumping an entire raw transcript into the model context.
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
- **Configuration**: content profile + style profile + renderer config
- **Architecture**: light interfaces, no heavy plugin framework

Do not overbuild dynamic discovery or generalized publishing until the basic OpenClaw/Codex → Hexo pipeline works well.

## Workflow

### 1. Choose the source path

Use one of these paths:

- **OpenClaw current/recent session**: use session tools to gather the bounded history you need, then reduce it before drafting
- **Codex transcript file**: parse JSONL/JSON/Markdown transcript files locally
- **Other sources**: only if they can be normalized into the same snapshot shape

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

Keep **content selection** separate from **writing style**:

- content profile decides what blocks appear
- style profile decides how the post sounds
- renderer decides the final output format

Use `references/configuration.md` for the current config layout and example values.

### 5. Render Hexo output

For Hexo output, produce:

- front matter
- title
- tags/categories
- body sections in a stable order

Write the generated file into the target Hexo repo's `source/_posts/` directory only after the content looks correct.

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
Config schema, example JSON, and mapping between content/style/renderer knobs.
