# Architecture

## Goals

Build a lightweight but extensible pipeline for turning agent conversations into technical blog drafts.

Primary goals for V1:

- support **OpenClaw** and **Codex** first
- avoid feeding full raw transcripts to the model
- generate **Hexo-compatible Markdown** first
- keep stable extension points without building a heavy plugin system
- allow an optional publish step after Markdown generation

## Non-goals for V1

- dynamic plugin loading
- many blog engines at once
- visual UI
- perfect automatic semantic understanding of every transcript
- fully automated publishing workflows beyond a few explicit backends

## Pipeline

```text
Source material
  -> SessionSnapshot
  -> IssueContext
  -> ArticleDraft
  -> Hexo Markdown
  -> optional Publisher
```

## Stable extension points

V1 should keep these extension points stable.

### 1. SourceAdapter

Responsibility:

- load transcript/session material
- normalize different source formats
- emit a `SessionSnapshot`

Initial implementations:

- `openclaw-session-history`
- `codex-jsonl`

### 2. ContextReducer

Responsibility:

- shrink large session material into a compact issue-oriented representation
- extract commands, files, errors, environment hints, timeline facts
- prepare compact reasoning input

### 3. StyleProfile

Responsibility:

- control tone, viewpoint, length, section phrasing, and writing preferences
- remain separate from factual content selection

Keep this separate from `ContentProfile`.

### 4. Renderer

Responsibility:

- convert an `ArticleDraft` or `IssueContext` into final Markdown
- apply target format rules
- write front matter and body

Initial implementation:

- `hexo-markdown`

### 5. Publisher

Responsibility:

- take rendered Markdown and optionally push it to a destination
- keep auth and transport outside the reducer
- support a small number of explicit backends
- obey the workflow mode (`draft`, `review`, `publish`)

Initial implementations:

- `git`
- `github-api`

## Core data model

### SessionSnapshot

Normalized input independent of source.

```json
{
  "source": "codex",
  "session_id": "rollout-...",
  "title": "fix hexo deploy bug",
  "metadata": {
    "repo": "hl128k/agent-blogger",
    "cwd": "/workspace/project",
    "agent": "codex",
    "model": "gpt-5"
  },
  "messages": [
    {
      "role": "user",
      "text": "...",
      "timestamp": "..."
    }
  ],
  "commands": [],
  "files": [],
  "errors": []
}
```

### IssueContext

Compact, blog-oriented intermediate structure.

```json
{
  "topic": "Hexo deploy failure",
  "summary": "One-paragraph factual summary",
  "symptoms": [],
  "investigation_steps": [],
  "failed_attempts": [],
  "root_cause": "...",
  "fix": "...",
  "files_changed": [],
  "commands_used": [],
  "environment": {},
  "lessons": [],
  "keywords": []
}
```

### ArticleDraft

Rendering-ready structure.

```json
{
  "title": "...",
  "excerpt": "...",
  "sections": [
    {
      "heading": "问题背景",
      "content": "..."
    }
  ],
  "tags": [],
  "categories": []
}
```

## Token-saving strategy

This project should not rely on dumping full chat history into the model.

Use these tactics first:

1. **bounded source selection**
   - choose the issue-relevant time range or message slice
2. **local extraction**
   - commands
   - files
   - errors
   - environment hints
3. **deduplication**
   - merge repeated error lines and repeated attempts
4. **lossy compression of long logs**
   - keep only representative lines
5. **draft from IssueContext, not raw transcript**

## OpenClaw strategy

For OpenClaw, prefer two modes:

### Live mode

- use `sessions_history` for the current or selected session
- bound the input to the relevant segment
- write the reduced context first
- draft the post second

### File mode

- if exact transcript bytes are needed, inspect transcript files on disk
- still reduce locally before drafting

## Codex strategy

For Codex, prefer transcript-file parsing first.

- parse JSONL/JSON transcripts locally
- extract message text, commands, files, errors
- later add hook-assisted sidecar summaries if useful

## Hexo strategy

V1 should write only Hexo-compatible Markdown.

Renderer concerns:

- front matter keys
- title/date/tags/categories
- stable section order
- output path under `source/_posts/`

Publishing concerns:

- keep outside the reducer
- be explicit and opt-in
- only push after the Markdown is written and verified

## Publisher strategy

Publisher concerns should stay separate from content reduction.

Keep these rules:

- auth is supplied through git credentials or an environment variable
- token secrets should not be hard-coded in config
- the same rendered file can be pushed by local git or GitHub Contents API
- the publish step should fail clearly if the destination repo or token is missing

## Recommended implementation bias

Prefer this tradeoff:

- **light interfaces**
- **deterministic local extraction**
- **config-driven rendering**
- **small, explicit publishing backends**
- **narrow V1 scope**

Avoid this in V1:

- generalized publish buses
- runtime plugin registries
- many backends at once
- complicated dependency trees
