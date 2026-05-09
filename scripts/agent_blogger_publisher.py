from __future__ import annotations

import base64
import json
import os
import subprocess
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from scripts.agent_blogger_core import IssueContext, slugify


@runtime_checkable
class Publisher(Protocol):
    def publish(
        self,
        config: dict[str, Any],
        issue: IssueContext,
        output_path: Path,
        publish: bool = False,
        no_publish: bool = False,
    ) -> None:
        ...


def publish_template_vars(issue: IssueContext, output_path: Path) -> dict[str, str]:
    now = datetime.now().astimezone()
    return {
        "title": issue.topic,
        "slug": slugify(issue.topic),
        "filename": output_path.name,
        "path": str(output_path),
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_publish_template(template: str, issue: IssueContext, output_path: Path) -> str:
    return template.format(**publish_template_vars(issue, output_path))


def workflow_mode(config: dict[str, Any]) -> str:
    workflow_config = config.get("workflow", {}) or {}
    mode = workflow_config.get("mode")
    if isinstance(mode, str) and mode.strip():
        normalized = mode.strip().lower()
        if normalized not in {"draft", "review", "publish"}:
            raise ValueError(f"unsupported workflow mode: {mode}")
        return normalized

    publish_config = config.get("publish", {}) or {}
    if publish_config.get("enabled", False):
        return "publish"
    return "draft"


def should_publish(config: dict[str, Any], publish: bool = False, no_publish: bool = False) -> bool:
    if no_publish:
        return False
    if publish:
        return True
    return workflow_mode(config) == "publish"


def git_config(publish_config: dict[str, Any]) -> dict[str, Any]:
    nested = publish_config.get("git")
    if isinstance(nested, dict):
        merged = dict(publish_config)
        merged.update(nested)
        return merged
    return publish_config


def resolve_git_repo_dir(git_cfg: dict[str, Any], output_path: Path) -> Path:
    configured = git_cfg.get("repo_dir")
    if configured:
        repo_dir = Path(configured).expanduser().resolve()
        if not (repo_dir / ".git").exists():
            raise FileNotFoundError(f"publish.git.repo_dir is not a git repository: {repo_dir}")
        return repo_dir

    current = output_path.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ValueError("publish.git.repo_dir is required unless output is inside a git repository")


def run_git(repo_dir: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def publish_git(publish_config: dict[str, Any], issue: IssueContext, output_path: Path) -> None:
    git_cfg = git_config(publish_config)
    repo_dir = resolve_git_repo_dir(git_cfg, output_path)
    resolved_output = output_path.resolve()
    try:
        rel_path = resolved_output.relative_to(repo_dir)
    except ValueError as exc:
        raise ValueError(f"output path must be inside publish.git.repo_dir: {resolved_output}") from exc

    run_git(repo_dir, ["add", str(rel_path)])
    status = run_git(repo_dir, ["status", "--porcelain", "--", str(rel_path)])
    if not status.stdout.strip():
        print("publish skipped: no git changes")
        return

    if git_cfg.get("commit", True):
        message_template = git_cfg.get("commit_message", "chore(blog): publish {title}")
        message = format_publish_template(message_template, issue, output_path)
        commit = run_git(repo_dir, ["commit", "-m", message, "--", str(rel_path)], check=False)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
        if commit.returncode == 0:
            print("published commit created")

    if git_cfg.get("push", True):
        remote = git_cfg.get("remote", "origin")
        branch = git_cfg.get("branch")
        refspec = f"HEAD:{branch}" if branch else "HEAD"
        run_git(repo_dir, ["push", remote, refspec])
        print(f"published git push to {remote} {refspec}")


def github_api_config(publish_config: dict[str, Any]) -> dict[str, Any]:
    nested = publish_config.get("github_api")
    if isinstance(nested, dict):
        merged = dict(publish_config)
        merged.update(nested)
        return merged
    return publish_config


def github_request(method: str, url: str, token: str, payload: dict[str, Any] | None = None, allow_404: bool = False) -> dict[str, Any] | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-blogger",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if allow_404 and exc.code == 404:
            return None
        raise RuntimeError(f"GitHub API {method} failed with HTTP {exc.code}: {body}") from exc


def publish_github_api(publish_config: dict[str, Any], issue: IssueContext, output_path: Path) -> None:
    api_cfg = github_api_config(publish_config)
    repo = api_cfg.get("repo")
    if not repo:
        raise ValueError("publish.github_api.repo is required for github-api mode")

    token_env = api_cfg.get("token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"environment variable {token_env} is required for github-api publishing")

    branch = api_cfg.get("branch", "main")
    path_template = api_cfg.get("path_template", "source/_posts/{filename}")
    repo_path = format_publish_template(path_template, issue, output_path).lstrip("/")
    encoded_path = urllib.parse.quote(repo_path, safe="/")
    base_url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"

    existing = github_request("GET", f"{base_url}?ref={urllib.parse.quote(branch)}", token, allow_404=True)
    content = output_path.read_bytes()
    payload: dict[str, Any] = {
        "message": format_publish_template(api_cfg.get("commit_message", "chore(blog): publish {title}"), issue, output_path),
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]

    github_request("PUT", base_url, token, payload=payload)
    print(f"published GitHub API commit to {repo}@{branch}:{repo_path}")


def publish_after_write(config: dict[str, Any], issue: IssueContext, output_path: Path, publish: bool = False, no_publish: bool = False) -> None:
    if not should_publish(config, publish=publish, no_publish=no_publish):
        return

    publish_config = config.get("publish", {}) or {}
    mode = publish_config.get("mode", "git")
    if mode in {"none", "disabled", "off"}:
        return
    if mode == "git":
        publish_git(publish_config, issue, output_path)
        return
    if mode in {"github-api", "github_api"}:
        publish_github_api(publish_config, issue, output_path)
        return
    raise ValueError(f"unsupported publish mode: {mode}")


class DefaultPublisher:
    def publish(
        self,
        config: dict[str, Any],
        issue: IssueContext,
        output_path: Path,
        publish: bool = False,
        no_publish: bool = False,
    ) -> None:
        publish_after_write(config, issue, output_path, publish=publish, no_publish=no_publish)


DEFAULT_PUBLISHER = DefaultPublisher()
