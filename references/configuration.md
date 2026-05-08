# Configuration

## Format

V1 uses JSON config.

Reasons:

- stdlib-only parser support
- easy to validate
- easy for agents to generate or patch
- can reference secrets through environment variables instead of storing raw tokens

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
      "environment",
      "files",
      "commands",
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
  },
  "publish": {
    "enabled": false,
    "mode": "git",
    "git": {
      "repo_dir": "/path/to/blog",
      "remote": "origin",
      "branch": "main",
      "commit": true,
      "push": true,
      "commit_message": "chore(blog): publish {title}"
    },
    "github_api": {
      "repo": "owner/repo",
      "branch": "main",
      "path_template": "source/_posts/{filename}",
      "token_env": "GITHUB_TOKEN",
      "commit_message": "chore(blog): publish {title}"
    }
  }
}
```

## Source config

Controls **where the transcript comes from**.

Recommended knobs:

- `type`
  - `codex-jsonl`, `generic-json`, `markdown-transcript`, or later `openclaw-session-history`
- `path`
  - local transcript path when using file mode

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

Controls **where and how Markdown is written**.

Recommended knobs:

- `type`
  - `hexo` for V1
- `post_dir`
  - target output folder inside the blog repo
- `slug_pattern`
  - filename strategy; supports `{date}` and `{slug}`
- `default_categories`
  - fallback categories
- `default_tags`
  - fallback tags
- `front_matter`
  - additional keys merged into Hexo front matter

## Publish config

Controls **what happens after the Markdown file is generated**.

This is intentionally separate from `renderer`:

- `renderer` writes the post file
- `publish` commits/pushes or calls an external publishing interface

### Common knobs

- `enabled`
  - default `false`; set `true` when you want `render-hexo` / `pipeline` to publish automatically
- `mode`
  - `git`: commit and push through a local blog repository
  - `github-api`: push the generated file through GitHub Contents API

CLI overrides:

```bash
# force publishing even when config says enabled=false
python3 scripts/agent_blogger.py pipeline session.jsonl --config agent-blogger.config.json --publish

# disable publishing even when config says enabled=true
python3 scripts/agent_blogger.py pipeline session.jsonl --config agent-blogger.config.json --no-publish
```

### `mode: git`

Use this when the blog repository already exists locally.

```json
{
  "publish": {
    "enabled": true,
    "mode": "git",
    "git": {
      "repo_dir": "/path/to/blog",
      "remote": "origin",
      "branch": "main",
      "commit": true,
      "push": true,
      "commit_message": "chore(blog): publish {title}"
    }
  }
}
```

Behavior:

1. write Markdown under the blog repo, usually `source/_posts/`
2. run `git add` for that file
3. create a commit if the file changed
4. run `git push origin HEAD:main`

Authentication is handled by existing git credentials, such as:

- SSH deploy key
- `gh auth login`
- git credential helper
- CI-provided git credentials

Do not put raw GitHub tokens in this JSON file.

### `mode: github-api`

Use this when you want to push directly to GitHub without requiring a local blog checkout.

```json
{
  "publish": {
    "enabled": true,
    "mode": "github-api",
    "github_api": {
      "repo": "owner/repo",
      "branch": "main",
      "path_template": "source/_posts/{filename}",
      "token_env": "GITHUB_TOKEN",
      "commit_message": "chore(blog): publish {title}"
    }
  }
}
```

Set the token outside the config:

```bash
export GITHUB_TOKEN="github_pat_xxx"
```

The token should be a fine-grained GitHub token with the minimum permissions needed to write contents to the target blog repository.

Template variables supported by `commit_message` and `path_template`:

- `{title}`
- `{slug}`
- `{filename}`
- `{path}`
- `{date}`
- `{datetime}`

## Good defaults for V1

For the first release, keep defaults conservative:

- one source at a time
- one post at a time
- one output format: Hexo Markdown
- one config file: JSON
- publish disabled by default
- secrets referenced by environment variable, not stored in the repo

## Notes on Hexo

The blog repo already knows how to build and deploy Markdown posts.

`agent-blogger` should only:

1. generate the source post file
2. optionally push that file to the blog repository or GitHub API

Hexo build/deploy should remain in the existing blog pipeline.
