# agent-blogger

把 AI Agent 的问题解决过程，整理成可以直接发布的 Hexo 博客草稿。

> 这个 README 是给人看的。`SKILL.md` 是给 OpenClaw / Agent 看的能力说明。

## 1. 项目介绍

在现在这个 AI 时代，很多问题已经不再是“一个人埋头钻研很久”，而是：

- 先发现问题
- 把报错、上下文和目标告诉 AI
- 让 AI 辅助分析、试错、修正
- 来回反复几轮，直到找到能落地的解法

这确实让解决问题的速度快了很多，但也带来一个很现实的问题：

**大量值得记录的排查过程，最后都只停留在聊天记录里。**

`agent-blogger` 想做的，就是把这些 AI Agent 会话中的有效信息抽出来，整理成结构清晰、可以发布的技术博客草稿。

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
```

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

### 可配置写作风格

文章内容和风格都可以配置，例如：

- 是否包含系统环境
- 是否包含开发环境
- 是否保留关键命令
- 是否保留文件变更
- 是否保留失败尝试
- 文章语气
- 文章长度
- 章节顺序
- 默认标签和分类

### 不负责自动发布

`agent-blogger` 只负责生成博客草稿。

构建、部署、发布应该继续交给现有博客仓库和部署流程，例如：

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

也就是说，**README 讲给人看，SKILL.md 讲给 Agent 看。**

### 3.2 手动运行（开发 / 调试）

如果你要本地验证解析、压缩或渲染效果，可以直接用脚本：

```bash
python3 scripts/agent_blogger.py init-config --output agent-blogger.config.json
python3 scripts/agent_blogger.py inspect /path/to/session.jsonl
python3 scripts/agent_blogger.py reduce /path/to/session.jsonl --config agent-blogger.config.json --output issue-context.json
python3 scripts/agent_blogger.py render-hexo issue-context.json --config agent-blogger.config.json --output /path/to/blog/source/_posts/example.md
python3 scripts/agent_blogger.py pipeline /path/to/session.jsonl --config agent-blogger.config.json --output /path/to/blog/source/_posts/example.md
```

支持的输入类型会按后缀自动识别：

- `.jsonl` → Codex 风格转录
- `.json` → 通用 JSON 会话
- 其他文本 → Markdown 风格会话记录

### 3.3 配置文件示例

`init-config` 会生成同样结构的示例配置。下面是一个完整但偏保守的默认配置：

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
  }
}
```

## 4. 技术栈

当前实现尽量保持轻量，优先使用标准库和简单可维护的结构。

- Python 3.10+
- JSON 配置
- Markdown 输出
- Hexo front matter
- Codex JSONL / JSON / Markdown 转录解析
- OpenClaw 会话历史适配
- 本地正则提取与上下文压缩

### 设计取向

- 轻接口
- 先归一化，再推理
- 内容选择和写作风格分离
- V1 先只做 OpenClaw / Codex → Hexo

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
- 各类 AI Coding / Vibe Coding 工具

最后，感谢那些原本只会沉在聊天记录里的问题解决过程。

它们也许不再需要被人手动整理一整晚，但仍然值得被记录下来。
