# agent-blogger

把 AI Agent 的问题解决过程，整理成可以发布、也可以直接推送到博客仓库的技术博客草稿。

> 这个 README 是给人看的。`SKILL.md` 是给 OpenClaw / Agent 看的能力说明。

## 1. 项目介绍

在现在这个 AI 时代，很多问题已经不再是“一个人埋头钻研很久”，而是：

- 先发现问题
- 把报错、上下文和目标告诉 AI
- 让 AI 辅助分析、试错、修正
- 来回反复几轮，直到找到能落地的解法

这确实让解决问题的速度快了很多，但也带来一个很现实的问题：

**大量值得记录的排查过程，最后都只停留在聊天记录里。**

`agent-blogger` 想做的，就是把这些 AI Agent 会话中的有效信息抽出来，整理成结构清晰、可以发布的技术博客草稿，并在配置允许时直接推送到博客仓库。

它不是要替代人的思考，也不是要把整段历史直接丢给模型；它更像是一个“共享的 AI 记忆整理器”——把问题背景、试错过程、根因判断和最终方案留下来，方便以后回看，也方便再喂给新的 AI。

本项目希望最终支持主流的 Vibe Coding 工具和主流博客框架。  
不过第一阶段会先聚焦这三个方向：

- **Codex**
- **OpenClaw**
- **Hexo**

当前 V1 的目标很明确：

```text
AI Agent 会话 / 转录记录
  -> 本地提取与压缩
  -> 结构化问题上下文
  -> Hexo Markdown 博客草稿
  -> 可选推送到博客仓库
```

### 当前原型状态

当前版本已经能作为 **OpenClaw / Agent 调用的雏形** 使用：输入 transcript 文件后，可以完成本地抽取、IssueContext 压缩、Hexo Markdown 渲染，以及可选发布。

需要明确的是，`current-session` 和 `openclaw-*` 这类来源都属于宿主 materialized-session，纯 CLI 不能凭空读取当前会话；在 OpenClaw 等宿主 Agent 场景中，应先由宿主把当前会话或指定会话片段 materialize 成文件或结构化上下文，再交给本工具处理。纯命令行调试时，建议始终传入明确的 `.jsonl`、`.json` 或 Markdown transcript 路径。

因此，接下来最值得优先打磨的不是扩展更多博客引擎，而是：

- 固定 OpenClaw 会话导出的输入约定
- 补充真实会话样本和回归测试
- 提升 reducer 对“根因 / 修复 / 失败尝试”的识别质量
- 在行为稳定后再拆分 `SourceAdapter`、`ContextReducer`、`Renderer`、`Publisher` 模块

先把这条链路跑顺，再考虑更广的扩展。

## 2. 核心特性

### 会话转博客草稿

从 Codex、OpenClaw 等 Agent 的会话记录中提取关键信息，整理成适合发布的技术文章。

重点保留：

- 问题背景
- 报错现象
- 排查过程
- 失败尝试
- 根因判断
- 解决方案
- 涉及文件
- 关键命令
- 经验总结

### 先本地提取，再交给模型

这个项目不主张把整份原始聊天记录直接喂给模型。

更推荐的流程是先在本地做一次整理：

- 提取命令
- 提取文件路径
- 提取错误信息
- 提取环境线索
- 去重重复内容
- 压缩过长日志

这样既能省 token，也能让最终文章更干净。

### 面向主流 Agent 输入

当前优先支持这些输入来源：

- OpenClaw 会话历史
- Codex JSONL / JSON 转录
- Markdown 风格的会话记录

后续如果要扩展到更多工具，也可以沿着同一套“先归一化、再压缩、再写稿”的思路继续做。

### 输出 Hexo Markdown

当前优先输出 Hexo 可直接使用的 Markdown，包含：

- front matter
- 标题
- 日期
- 标签
- 分类
- 正文结构

默认会写到博客仓库的：

```text
source/_posts/
```

### 可选自动推送

如果配置了 `publish`，生成 Markdown 后可以继续执行推送动作。

当前支持两种方式：

- `git`：写入本地博客仓库后 `git add` / `git commit` / `git push`
- `github-api`：通过 GitHub Contents API 直接写入远端仓库

GitHub token 不建议直接写进配置文件，而是通过环境变量引用，例如 `GITHUB_TOKEN`。

### 可配置写作风格与模板

文章内容、写作风格、提示词和博文模板都可以配置，例如：

- 是否包含系统环境
- 是否包含开发环境
- 是否保留关键命令
- 是否保留文件变更
- 是否保留失败尝试
- 文章语气
- 文章长度
- 章节顺序
- 章节标题
- 章节正文模板
- 草稿生成提示词
- 默认标签和分类

### 不负责构建和部署

`agent-blogger` 可以把生成好的 Markdown 推送到博客仓库，但不接管 Hexo 构建和站点部署。

构建、部署、发布站点本身应该继续交给现有博客仓库和 CI/CD 流程，例如：

- Hexo
- GitHub Actions
- Cloudflare Pages
- 其他静态站点部署方案

## 3. 使用配置

### 3.1 作为 Agent 技能使用（推荐）

这是日常主用方式。

把本仓库放到 OpenClaw / Codex 可识别的 skills 目录中，确保 `SKILL.md` 可以被读取，然后直接让 Agent 按技能说明完成：

- 读取会话
- 提取上下文
- 压缩成问题摘要
- 输出 Hexo Markdown
- 如果配置允许，推送到博客仓库

也就是说，**README 讲给人看，SKILL.md 讲给 Agent 看。**

### 3.2 手动运行（开发 / 调试）

如果你要本地验证解析、压缩、渲染或推送效果，可以直接用脚本：

```bash
cp agent-blogger.config.example.yaml agent-blogger.config.yaml
python3 scripts/agent_blogger.py inspect transcripts/codex-session.jsonl
python3 scripts/agent_blogger.py reduce transcripts/codex-session.jsonl --config agent-blogger.config.yaml --output issue-context.json
python3 scripts/agent_blogger.py render-hexo issue-context.json --config agent-blogger.config.yaml --output /path/to/blog/source/_posts/example.md
python3 scripts/agent_blogger.py pipeline transcripts/codex-session.jsonl --config agent-blogger.config.yaml --output /path/to/blog/source/_posts/example.md
```

仓库根目录提供了 `agent-blogger.config.example.yaml` 作为可复制的示例配置。你也可以用 `python3 scripts/agent_blogger.py init-config --output agent-blogger.config.yaml` 重新生成同等结构的本地配置文件。

验证核心行为：

```bash
python3 -m unittest discover -s tests -v
```

强制推送或禁用推送：

```bash
python3 scripts/agent_blogger.py pipeline /path/to/session.jsonl --config agent-blogger.config.yaml --publish
python3 scripts/agent_blogger.py pipeline /path/to/session.jsonl --config agent-blogger.config.yaml --no-publish
```

支持的输入类型会按后缀自动识别：

- `.jsonl` → Codex 风格转录
- `.json` → 通用 JSON 会话
- 其他文本 → Markdown 风格会话记录

输入来源优先级：

```text
CLI --source-path or positional INPUT > config source.path > host current session
CLI --source > config source.type > current-session
CLI --session-key > config source.session_key
CLI --base-dir > config source.base_dir
```

source 值分两类：

- 文件模式：`auto`、`codex-jsonl`、`generic-json`、`markdown-transcript`
- 宿主 materialized-session：`current-session`、`openclaw-current-session`、`openclaw-session`、`openclaw-session-history`

说明：`base_dir` 只解析相对 transcript 文件路径；`session_key` 只是宿主会话身份/元数据，不参与本地路径查找。

### 3.3 配置文件示例

`init-config` 默认会生成 **YAML** 示例配置；脚本同时兼容 JSON。下面是一个完整但偏保守的默认配置：

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

### 3.4 工作流模式

`workflow.mode` 控制默认行为：

- `draft`：只生成 Markdown
- `review`：生成 Markdown，等待 `--publish`
- `publish`：生成后自动推送

### 3.5 推送方式

#### 本地 git 推送

适合博客仓库已经 clone 到本地的情况。

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

认证交给现有 git 环境，例如 SSH key、`gh auth login` 或 git credential helper。

#### GitHub API 推送

适合没有本地博客仓库，只想直接写入 GitHub 的情况。

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

然后在运行环境里设置：

```bash
export GITHUB_TOKEN="github_pat_xxx"
```

建议使用 GitHub fine-grained token，只给目标博客仓库的 Contents 写权限。

## 4. 技术栈

当前实现尽量保持轻量，优先使用标准库和简单可维护的结构。

- Python 3.10+
- YAML 配置（JSON 兼容）
- 可配置 prompt/template profile
- Markdown 输出
- Hexo front matter
- Codex JSONL / JSON / Markdown 转录解析
- OpenClaw 会话历史适配
- 本地正则提取与上下文压缩
- Git / GitHub Contents API 推送

### 设计取向

- 轻接口
- 先归一化，再推理
- 内容选择和写作风格分离
- 渲染和推送分离
- V1 先只做 OpenClaw / Codex → Hexo → 可选推送

当前不打算在第一阶段引入这些东西：

- 重插件系统
- 多博客引擎并行支持
- Web UI
- 数据库
- 复杂自动发布平台

## 5. 许可证与致谢

本项目使用 **MIT License**。

也感谢这些工具和项目提供的灵感：

- OpenClaw
- Codex
- Hexo
- GitHub
- 各类 AI Coding / Vibe Coding 工具

最后，感谢那些原本只会沉在聊天记录里的问题解决过程。

它们也许不再需要被人手动整理一整晚，但仍然值得被记录下来。
