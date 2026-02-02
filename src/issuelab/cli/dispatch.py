"""
向用户 fork 仓库分发 repository_dispatch 事件

读取注册信息，向匹配的用户仓库发送 repository_dispatch 事件。
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import yaml


def load_registry(registry_dir: Path) -> dict[str, dict[str, Any]]:
    """
    加载所有注册文件

    Args:
        registry_dir: 注册目录路径

    Returns:
        用户名 -> 注册信息的字典
    """
    registry = {}

    if not registry_dir.exists():
        print(f"Warning: Registry directory not found: {registry_dir}", file=sys.stderr)
        return registry

    for yml_file in registry_dir.glob("*.yml"):
        if yml_file.name == "README.md":
            continue

        try:
            with open(yml_file) as f:
                config = yaml.safe_load(f)

            if not config:
                print(f"Warning: Empty config in {yml_file.name}", file=sys.stderr)
                continue

            username = config.get("username")
            if not username:
                print(f"Warning: {yml_file.name} missing username", file=sys.stderr)
                continue

            # 检查是否启用
            if not config.get("enabled", True):
                print(f"Info: {username} is disabled", file=sys.stderr)
                continue

            registry[username] = config

        except yaml.YAMLError as e:
            print(f"Error parsing {yml_file.name}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Error loading {yml_file.name}: {e}", file=sys.stderr)
            continue

    return registry


def match_triggers(mentions: list[str], registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """
    匹配 mentions 到注册的用户

    Args:
        mentions: @mention 列表（不含 @）
        registry: 用户注册信息

    Returns:
        匹配的用户配置列表
    """
    matched = []
    matched_users = set()

    for mention in mentions:
        # 直接匹配用户名
        if mention in registry:
            config = registry[mention]
            triggers = config.get("triggers", [])

            # 检查是否在触发列表中
            if f"@{mention}" in triggers and mention not in matched_users:
                matched.append(config)
                matched_users.add(mention)
                continue

        # 检查所有用户的触发条件
        for username, config in registry.items():
            if username in matched_users:
                continue

            triggers = config.get("triggers", [])
            if f"@{mention}" in triggers:
                matched.append(config)
                matched_users.add(username)
                break

    return matched


def dispatch_event(
    repository: str, event_type: str, client_payload: dict[str, Any], token: str, timeout: int = 10
) -> bool:
    """
    发送 repository_dispatch 事件

    Args:
        repository: 目标仓库（owner/repo）
        event_type: 事件类型
        client_payload: 事件数据
        token: GitHub Token
        timeout: 超时时间（秒）

    Returns:
        是否成功
    """
    url = f"https://api.github.com/repos/{repository}/dispatches"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {"event_type": event_type, "client_payload": client_payload}

    try:
        response = requests.post(url, headers=headers, json=data, timeout=timeout)
        response.raise_for_status()
        print(f"✓ Dispatched to {repository}")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP error dispatching to {repository}: {e}", file=sys.stderr)
        if response.text:
            print(f"  Response: {response.text}", file=sys.stderr)
        return False
    except requests.exceptions.Timeout:
        print(f"✗ Timeout dispatching to {repository}", file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to dispatch to {repository}: {e}", file=sys.stderr)
        return False


def write_github_output(dispatched: int, total: int) -> None:
    """
    写入 GitHub Actions 输出变量

    Args:
        dispatched: 成功分发的数量
        total: 总匹配数量
    """
    if "GITHUB_OUTPUT" not in os.environ:
        return

    try:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"dispatched_count={dispatched}\n")
            f.write(f"total_count={total}\n")
    except OSError as e:
        print(f"Warning: Failed to write GitHub output: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """
    CLI 入口点

    Args:
        argv: 命令行参数，None 则使用 sys.argv

    Returns:
        退出码，0 表示成功
    """
    parser = argparse.ArgumentParser(description="Dispatch events to user repositories")
    parser.add_argument("--mentions", required=True, help="Mentions list (JSON array or comma-separated)")
    parser.add_argument(
        "--registry-dir", default="agents/_registry", help="Registry directory (default: agents/_registry)"
    )
    parser.add_argument("--source-repo", required=True, help="Source repository (owner/repo)")
    parser.add_argument("--issue-number", required=True, type=int, help="Issue number")
    parser.add_argument("--issue-title", help="Issue title")
    parser.add_argument("--issue-body", help="Issue body")
    parser.add_argument("--comment-id", type=int, help="Comment ID (if triggered by comment)")
    parser.add_argument("--comment-body", help="Comment body")
    parser.add_argument("--labels", help="Issue labels (JSON array)")
    parser.add_argument("--event-type", default="issue_mention", help="Dispatch event type (default: issue_mention)")

    args = parser.parse_args(argv)

    # 读取 GitHub Token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        return 1

    # 解析 mentions（支持 JSON 和 CSV 格式）
    mentions_str = args.mentions.strip()
    if mentions_str.startswith("[") and mentions_str.endswith("]"):
        # JSON 数组格式
        try:
            mentions = json.loads(mentions_str)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in mentions: {args.mentions}", file=sys.stderr)
            print(f"  {e}", file=sys.stderr)
            return 1
    else:
        # CSV 格式（逗号分隔）
        mentions = [m.strip() for m in mentions_str.split(",") if m.strip()]

    if not mentions:
        print("Info: No mentions found, nothing to dispatch")
        return 0

    print(f"Found mentions: {', '.join(mentions)}")

    # 加载注册信息
    registry_dir = Path(args.registry_dir)
    registry = load_registry(registry_dir)
    print(f"Loaded {len(registry)} registered agents")

    if not registry:
        print("Warning: No agents registered")
        return 0

    # 匹配用户
    matched_configs = match_triggers(mentions, registry)

    if not matched_configs:
        print("Info: No matching agents found")
        return 0

    print(f"Matched {len(matched_configs)} agents")

    # 构建 client_payload
    client_payload = {
        "source_repo": args.source_repo,
        "issue_number": args.issue_number,
        "issue_title": args.issue_title,
        "issue_body": args.issue_body,
    }

    if args.comment_id:
        client_payload["comment_id"] = args.comment_id
        client_payload["comment_body"] = args.comment_body

    if args.labels:
        try:
            client_payload["labels"] = json.loads(args.labels)
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in labels: {args.labels}", file=sys.stderr)

    # 分发事件
    success_count = 0
    for config in matched_configs:
        repository = config.get("repository")
        branch = config.get("branch", "main")
        username = config.get("username")

        if not repository:
            print(f"Warning: {username} has no repository configured", file=sys.stderr)
            continue

        # 添加用户特定信息
        payload = client_payload.copy()
        payload["target_username"] = username
        payload["target_branch"] = branch

        # 发送 dispatch
        if dispatch_event(repository, args.event_type, payload, token):
            success_count += 1

    print(f"\nDispatched to {success_count}/{len(matched_configs)} agents")

    # 写入 GitHub Actions 输出
    write_github_output(success_count, len(matched_configs))

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
