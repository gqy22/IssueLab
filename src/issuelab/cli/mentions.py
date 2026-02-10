"""
解析 Issue/Comment 中的 @mentions (GitHub 用户名)

用于跨仓库触发：提取 GitHub 用户名用于分发到用户仓库
与 issuelab.parser 的区别：
- parser.py: 解析 Agent 真名（不支持别名）
- mentions.py: 解析 GitHub 用户名（@alice, @bob）
"""

import argparse
import json
import os
import sys

from issuelab.utils.mentions import extract_controlled_mentions, extract_github_mentions


def parse_github_mentions(text: str, controlled_section_only: bool = False) -> list[str]:
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
    if controlled_section_only:
        return extract_controlled_mentions(text)
    return extract_github_mentions(text)


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
    parser.add_argument(
        "--controlled-section-only",
        action="store_true",
        help="Only parse mentions from controlled sections (相关人员/协作请求)",
    )

    args = parser.parse_args(argv)

    # 从文件读取 body 内容
    issue_body = args.issue_body
    if args.issue_body_file:
        try:
            with open(args.issue_body_file, encoding="utf-8") as f:
                issue_body = f.read()
        except Exception as e:
            print(f"Error reading issue-body-file: {e}", file=sys.stderr)
            return 1

    comment_body = args.comment_body
    if args.comment_body_file:
        try:
            with open(args.comment_body_file, encoding="utf-8") as f:
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
    mentions = parse_github_mentions(text, controlled_section_only=args.controlled_section_only)

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
