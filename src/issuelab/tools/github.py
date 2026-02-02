"""GitHub 操作工具"""

import json
import os
import subprocess

from issuelab.logging_config import get_logger
from issuelab.retry import retry_sync

logger = get_logger(__name__)


@retry_sync(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
def get_issue_info(issue_number: int) -> dict:
    """获取 Issue 信息（带重试机制）"""
    logger.debug(f"获取 Issue #{issue_number} 信息")
    # 优先使用 GH_TOKEN，fallback 到 GITHUB_TOKEN
    env = os.environ.copy()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "number,title,body,labels,comments"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        logger.error(f"获取 Issue #{issue_number} 失败: {result.stderr}")
        raise RuntimeError(f"Failed to get issue info: {result.stderr}")
    return json.loads(result.stdout)


def post_comment(issue_number: int, body: str) -> str:
    """在 Issue 下发布评论"""
    # 优先使用 GH_TOKEN，fallback 到 GITHUB_TOKEN
    env = os.environ.copy()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body], capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Comment posted to issue #{issue_number}"


def update_label(issue_number: int, label: str, action: str = "add") -> str:
    """更新 Issue 标签"""
    action_flag = "--add-label" if action == "add" else "--remove-label"
    # 优先使用 GH_TOKEN，fallback 到 GITHUB_TOKEN
    env = os.environ.copy()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh", "issue", "edit", str(issue_number), action_flag, label], capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Label '{label}' {action}ed on issue #{issue_number}"
