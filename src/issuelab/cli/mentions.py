"""
解析 Issue/Comment 中的 @mentions (GitHub 用户名)

用于跨仓库触发：提取 GitHub 用户名用于分发到用户仓库
与 issuelab.parser 的区别：
- parser.py: 解析 Agent 别名（@mod -> moderator）
- mentions.py: 解析 GitHub 用户名（@alice, @bob）
"""

import argparse
import json
import os
import re
import sys


def parse_github_mentions(text: str) -> list[str]:
    """
    从文本中提取所有 GitHub @mentions

    用于跨仓库分发，提取真实的 GitHub 用户名

    Args:
        text: 要解析的文本

    Returns:
        提取到的 GitHub 用户名列表（不包含 @），去重保持顺序

    Example:
        >>> parse_github_mentions("@alice and @bob, please review")
        ['alice', 'bob']
        >>> parse_github_mentions("@alice @alice @bob")
        ['alice', 'bob']
    """
    if not text:
        return []

    # 匹配 @username 模式
    # GitHub 用户名规则：字母、数字、连字符、下划线，不能以连字符或下划线开头或结尾
    pattern = r"@([a-zA-Z0-9_](?:[a-zA-Z0-9_-]*[a-zA-Z0-9_])?)"
    matches = re.findall(pattern, text)

    # 去重并保持顺序
    seen = set()
    result = []
    for username in matches:
        if username not in seen:
            seen.add(username)
            result.append(username)

    return result


def write_github_output(mentions: list[str]) -> None:
    """
    写入 GitHub Actions 输出变量

    Args:
        mentions: mention 列表
    """
    if "GITHUB_OUTPUT" not in os.environ:
        return

    try:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            # 使用逗号分隔格式，避免 shell 引号问题
            f.write(f"mentions={','.join(mentions)}\n")
            f.write(f"count={len(mentions)}\n")
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
    parser = argparse.ArgumentParser(description="Parse @mentions from GitHub Issue/Comment")
    parser.add_argument("--issue-body", help="Issue body text", default="")
    parser.add_argument("--issue-body-file", help="Issue body text (read from file)", default="")
    parser.add_argument("--comment-body", help="Comment body text", default="")
    parser.add_argument("--comment-body-file", help="Comment body text (read from file)", default="")
    parser.add_argument("--output", default="csv", choices=["json", "csv", "text"], help="Output format (default: csv)")

    args = parser.parse_args(argv)

    # 从文件读取 body 内容
    issue_body = args.issue_body
    if args.issue_body_file:
        try:
            with open(args.issue_body_file, "r", encoding="utf-8") as f:
                issue_body = f.read()
        except Exception as e:
            print(f"Error reading issue-body-file: {e}", file=sys.stderr)
            return 1

    comment_body = args.comment_body
    if args.comment_body_file:
        try:
            with open(args.comment_body_file, "r", encoding="utf-8") as f:
                comment_body = f.read()
        except Exception as e:
            print(f"Error reading comment-body-file: {e}", file=sys.stderr)
            return 1

    # 合并 Issue body 和 Comment body
    text = issue_body + "\n" + comment_body

    if not text.strip():
        print("Error: No text provided", file=sys.stderr)
        return 1

    # 解析 mentions（使用新的函数名）
    mentions = parse_github_mentions(text)

    # 输出
    if args.output == "json":
        print(json.dumps({"mentions": mentions, "count": len(mentions)}))
    elif args.output == "csv":
        # 逗号分隔格式，适合 shell 使用
        print(",".join(mentions))
    else:  # text
        for mention in mentions:
            print(mention)

    # 写入 GitHub Actions 输出
    write_github_output(mentions)

    return 0


if __name__ == "__main__":
    sys.exit(main())
