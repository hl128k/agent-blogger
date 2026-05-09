# Configuration

## Format

V1 recommends YAML config, while keeping JSON compatible for older setups.

The repository includes `agent-blogger.config.example.yaml` as a copyable baseline. For local use, copy it to `agent-blogger.config.yaml` and adjust paths, output folders, and publish settings.

Reasons:

- human-friendly for layered config
- easy to validate
- easy for agents to generate or patch
- can reference secrets through environment variables instead of storing raw tokens

## Example

```yaml
source:
  type: codex-jsonl
  path: null
  session_key: null
  base_dir: .
content_profile:
  include_system_env: true
  include_dev_env: true
  include_commands: true
  include_file_changes: true
  include_failed_attempts: true
  include_timeline: false
  include_raw_logs: false
  max_message_chars: 4000
style_profile:
  tone: 简洁、直接、偏实战
  perspective: first-person
  language: zh-CN
  verbosity: medium
  intro_style: problem-first
template_profile:
  type: hexo-technical-post
  section_order:
  - background
  - symptoms
  - investigation
  - root_cause
  - fix
  - environment
  - files
  - commands
  - lesson
  section_headings:
    background: 背景
    symptoms: 问题现象
    investigation: 排查过程
    root_cause: 根因判断
    fix: 解决方案
    environment: 环境信息
    files: 涉及文件
    commands: 关键命令
    lesson: 复盘与经验
  section_templates:
    background: '{summary}


      这篇记录采用 **{tone}** 的复盘方式，重点保留问题、处理过程和最终结论。'
  optional_sections:
  - environment
  - files
  - commands
prompt_profile:
  system_prompt: 你是一名技术博客编辑，把结构化问题上下文整理成清晰、真实、可复盘的技术文章。不要编造不存在的环境、命令或结论。
  draft_prompt_template: 请根据下面的 IssueContext 写一篇 {language} 技术博客。语气：{tone}。视角：{perspective}。模板：{template_type}。章节顺序：{section_order}。
  include_reduced_context: true
renderer:
  type: hexo
  post_dir: source/_posts
  slug_pattern: '{date}-{slug}'
  default_categories:
  - AI开发
  - Agent实践
  default_tags:
  - agent-blogger
  front_matter:
    author: hl128k
    comments: true
    toc: true
workflow:
  mode: review
publish:
  enabled: false
  mode: git
  git:
    repo_dir: /path/to/blog
    remote: origin
    branch: main
    commit: true
    push: true
    commit_message: 'chore(blog): publish {title}'
  github_api:
    repo: owner/repo
    branch: main
    path_template: source/_posts/{filename}
    token_env: GITHUB_TOKEN
    commit_message: 'chore(blog): publish {title}'
```

## Source config

Controls **where the transcript comes from**.

Recommended knobs:

- `type`
  - file mode values: `auto`, `codex-jsonl`, `generic-json`, `markdown-transcript`
  - host materialized-session values: `current-session`, `openclaw-current-session`, `openclaw-session`, `openclaw-session-history`
- `path`
  - optional local transcript path when using file mode
- `session_key`
  - `session_key is host session identity/metadata and does not participate in local path lookup`
  - optional host session identity/metadata; CLI `--session-key` overrides this value
- `base_dir`
  - base_dir only resolves relative transcript file paths

Resolution precedence:

```text
CLI --source-path or positional INPUT > config source.path > host current session
CLI --source > config source.type > current-session
CLI --session-key > config source.session_key
CLI --base-dir > config source.base_dir
```

For a pure CLI run, `current-session` must be materialized by the host agent first; otherwise provide `INPUT`, `--source-path`, or `source.path`.

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

## Template profile

Controls **the blog skeleton and section presets**.

Recommended knobs:

- `type`
  - template preset name, such as `hexo-technical-post`
- `section_order`
  - ordered section keys used by the renderer
- `section_headings`
  - maps section keys to visible Markdown headings
- `section_templates`
  - optional per-section text templates; supports variables like `{summary}`, `{tone}`, `{root_cause}`, `{fix}`, `{environment}`
- `optional_sections`
  - sections that should disappear when their source facts are empty

Keep template decisions separate from content extraction:

- `content_profile` decides whether system/dev environment facts are collected
- `template_profile` decides where those facts appear in the final post

## Prompt profile

Controls **the prompt used between summary reduction and final prose generation**.

Recommended knobs:

- `system_prompt`
  - stable role/instruction prompt for the blog editor agent
- `draft_prompt_template`
  - user-facing drafting instruction template; supports the same variables as `section_templates`
- `include_reduced_context`
  - append the reduced `IssueContext` JSON to the generated prompt

The CLI can render this prompt without writing a post:

```bash
python3 scripts/agent_blogger.py render-prompt issue-context.json --config agent-blogger.config.yaml
```

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

## Workflow config

Controls **whether the run stops at a draft, waits for review, or publishes automatically**.

Recommended knob:

- `mode`
  - `draft`: only write Markdown
  - `review`: write Markdown and wait for explicit `--publish`
  - `publish`: write Markdown and publish automatically

## Publish config

Controls **how the Markdown file is pushed after generation**.

This is intentionally separate from `renderer`:

- `renderer` writes the post file
- `publish` commits/pushes or calls an external publishing interface

### Common knobs

- `enabled`
  - legacy alias for auto-publish; prefer `workflow.mode`
- `mode`
  - `git`: commit and push through a local blog repository
  - `github-api`: push the generated file through GitHub Contents API

CLI overrides:

```bash
# force publishing even when config says enabled=false
python3 scripts/agent_blogger.py pipeline session.jsonl --config agent-blogger.config.yaml --publish

# disable publishing even when config says enabled=true
python3 scripts/agent_blogger.py pipeline session.jsonl --config agent-blogger.config.yaml --no-publish
```

### `mode: git`

Use this when the blog repository already exists locally.

```yaml
publish:
  enabled: true
  mode: git
  git:
    repo_dir: /path/to/blog
    remote: origin
    branch: main
    commit: true
    push: true
    commit_message: 'chore(blog): publish {title}'
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

Do not put raw GitHub tokens in this config file.

### `mode: github-api`

Use this when you want to push directly to GitHub without requiring a local blog checkout.

```yaml
publish:
  enabled: true
  mode: github-api
  github_api:
    repo: owner/repo
    branch: main
    path_template: source/_posts/{filename}
    token_env: GITHUB_TOKEN
    commit_message: 'chore(blog): publish {title}'
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
- one config file: YAML, with JSON compatibility
- workflow defaults to `review`
- publish disabled by default
- secrets referenced by environment variable, not stored in the repo

## Notes on Hexo

The blog repo already knows how to build and deploy Markdown posts.

`agent-blogger` should only:

1. generate the source post file
2. optionally push that file to the blog repository or GitHub API

Hexo build/deploy should remain in the existing blog pipeline.
