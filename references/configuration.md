# Configuration

## Format

Use JSON for V1 configs.

Reason:

- stdlib-only parser support
- easy to validate
- simple for agent-generated output

## Example

```json
{
  "source": {
    "type": "codex-jsonl",
    "path": "/path/to/session.jsonl"
  },
  "content_profile": {
    "include_system_env": true,
    "include_dev_env": true,
    "include_commands": true,
    "include_file_changes": true,
    "include_failed_attempts": true,
    "include_timeline": false,
    "include_raw_logs": false,
    "max_message_chars": 4000
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
      "lesson"
    ]
  },
  "renderer": {
    "type": "hexo",
    "post_dir": "source/_posts",
    "slug_pattern": "{date}-{slug}",
    "default_categories": ["AI开发", "Agent实践"],
    "default_tags": ["agent-blogger"],
    "front_matter": {
      "author": "hl128k",
      "comments": true,
      "toc": true
    }
  }
}
```

## Content profile

Controls **what facts to keep**.

Recommended knobs:

- `include_system_env`
  - include OS/runtime/host hints when present
- `include_dev_env`
  - include language/toolchain/repo hints when present
- `include_commands`
  - keep important commands
- `include_file_changes`
  - keep touched file names and paths
- `include_failed_attempts`
  - preserve the main dead ends
- `include_timeline`
  - keep sequence ordering when useful
- `include_raw_logs`
  - avoid this unless a log line is essential
- `max_message_chars`
  - truncate overly long messages before reduction

## Style profile

Controls **how the post sounds**.

Recommended knobs:

- `tone`
  - e.g. `简洁、直接、偏实战`
- `perspective`
  - e.g. `first-person` or `neutral`
- `language`
  - default `zh-CN`
- `verbosity`
  - `short`, `medium`, `long`
- `intro_style`
  - `problem-first`, `story-first`, `decision-first`
- `section_order`
  - explicit order of final article sections

## Renderer config

Controls **where and how the Markdown is written**.

Recommended knobs:

- `type`
  - `hexo` for V1
- `post_dir`
  - target output folder inside the blog repo
- `slug_pattern`
  - filename strategy
- `default_categories`
  - fallback categories
- `default_tags`
  - fallback tags
- `front_matter`
  - additional keys to merge into Hexo front matter

## Good defaults for this project

For the first release, keep the defaults conservative:

- one source at a time
- one post at a time
- one output format: Hexo Markdown
- one config file: JSON
- one article style profile per run

## Notes on Hexo

The blog repo already builds posts from Markdown files.
This project should only write the source post file and let the existing blog pipeline build/deploy it.
