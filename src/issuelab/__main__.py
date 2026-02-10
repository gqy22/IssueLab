"""主入口：支持多种子命令"""

import argparse
import json
import os

from issuelab.commands.core import handle_execute, handle_list_agents, handle_review
from issuelab.commands.observer import handle_observe, handle_observe_batch
from issuelab.commands.personal import handle_personal_reply, handle_personal_scan
from issuelab.config import Config
from issuelab.logging_config import get_logger, setup_logging
from issuelab.tools.github import get_issue_info

# 初始化日志
setup_logging(level=Config.get_log_level(), log_file=Config.get_log_file())
logger = get_logger(__name__)


def parse_agents_arg(agents_str: str) -> list[str]:
    """
    解析 agents 参数，支持多种格式

    Args:
        agents_str: agents 字符串，支持:
            - 逗号分隔: "moderator,reviewer_a"
            - 空格分隔: "moderator reviewer_a"
            - JSON 数组: '["moderator", "reviewer_a"]'

    Returns:
        agent 名称列表（小写）
    """
    agents_str = agents_str.strip()

    if agents_str.startswith("[") and agents_str.endswith("]"):
        try:
            agents = json.loads(agents_str)
            return [agent.lower() for agent in agents]
        except json.JSONDecodeError:
            logger.warning(f"JSON 格式解析失败，尝试其他格式: {agents_str}")

    if "," in agents_str:
        return [a.strip().lower() for a in agents_str.split(",") if a.strip()]

    return [a.lower() for a in agents_str.split() if a]


def _prepare_issue_execution_context(issue_number: int) -> tuple[dict, str, str, str, int]:
    """Load issue info and write context file for agent execution commands."""
    print(f"[INFO] 正在获取 Issue #{issue_number} 信息...")
    issue_info = get_issue_info(issue_number, format_comments=True)
    from issuelab.tools.github import write_issue_context_file

    issue_file = write_issue_context_file(
        issue_number=issue_number,
        title=issue_info.get("title", ""),
        body=issue_info.get("body", ""),
        comments=issue_info.get("comments", ""),
        comment_count=issue_info.get("comment_count", 0),
    )
    context = f"**Issue 内容文件**: {issue_file}\n请使用 Read 工具读取该文件后再进行分析。"
    comments = issue_info.get("comments", "")
    comment_count = issue_info.get("comment_count", 0)
    print(f"[OK] 已获取: 标题={issue_info.get('title', '')[:30]}..., 评论数={comment_count}")
    return issue_info, issue_file, context, comments, comment_count


def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    execute_parser = subparsers.add_parser("execute", help="并行执行代理")
    execute_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    execute_parser.add_argument("--agents", type=str, required=True, help="代理名称（逗号分隔）")
    execute_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    review_parser = subparsers.add_parser("review", help="运行顺序评审流程")
    review_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    review_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    observe_parser = subparsers.add_parser("observe", help="运行 Observer Agent 分析 Issue")
    observe_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    observe_parser.add_argument("--post", action="store_true", help="自动发布触发评论到 Issue")

    observe_batch_parser = subparsers.add_parser("observe-batch", help="并行分析多个 Issues")
    observe_batch_parser.add_argument("--issues", type=str, required=True, help="Issue 编号列表（逗号分隔）")
    observe_batch_parser.add_argument(
        "--max-parallel",
        type=int,
        default=int(os.environ.get("ISSUELAB_OBSERVER_MAX_PARALLEL", "5")),
        help="Observer 并行分析上限（默认 5，可用 ISSUELAB_OBSERVER_MAX_PARALLEL 覆盖）",
    )
    observe_batch_parser.add_argument(
        "--auto-trigger",
        action="store_true",
        help="自动触发 agent（system 走 workflow dispatch，user 走 repository dispatch）",
    )

    subparsers.add_parser("list-agents", help="列出所有可用的 Agent")

    personal_scan_parser = subparsers.add_parser("personal-scan", help="个人agent扫描主仓库issues（用于fork仓库）")
    personal_scan_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_scan_parser.add_argument("--issues", type=str, required=True, help="候选issue编号（逗号分隔）")
    personal_scan_parser.add_argument("--max-replies", type=int, default=3, help="最多回复的issue数量（默认3）")
    personal_scan_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )

    personal_reply_parser = subparsers.add_parser("personal-reply", help="个人agent回复主仓库issue（用于fork仓库）")
    personal_reply_parser.add_argument("--agent", type=str, required=True, help="个人agent名称")
    personal_reply_parser.add_argument("--issue", type=int, required=True, help="Issue编号")
    personal_reply_parser.add_argument(
        "--repo", type=str, default="gqy20/IssueLab", help="主仓库名称（默认gqy20/IssueLab）"
    )
    personal_reply_parser.add_argument("--issue-title", type=str, default="", help="Issue标题（可选，用于优化）")
    personal_reply_parser.add_argument("--issue-body", type=str, default="", help="Issue内容（可选，用于优化）")
    personal_reply_parser.add_argument(
        "--available-agents", type=str, default="", help="系统中可用的智能体列表（JSON格式）"
    )
    personal_reply_parser.add_argument("--post", action="store_true", help="自动发布回复到主仓库")

    args = parser.parse_args()

    if args.command == "execute":
        _, _, context, _, comment_count = _prepare_issue_execution_context(args.issue)
        return handle_execute(args, context, comment_count, parse_agents_arg)

    if args.command == "review":
        _, _, context, _, comment_count = _prepare_issue_execution_context(args.issue)
        handle_review(args, context, comment_count)
        return None

    if args.command == "observe":
        issue_info, issue_file, _, comments, _ = _prepare_issue_execution_context(args.issue)
        handle_observe(args, issue_info, issue_file, comments)
        return None

    if args.command == "observe-batch":
        handle_observe_batch(args)
        return None

    if args.command == "personal-scan":
        return handle_personal_scan(args)

    if args.command == "personal-reply":
        return handle_personal_reply(args)

    if args.command == "list-agents":
        handle_list_agents()
        return None

    parser.print_help()
    return None


if __name__ == "__main__":
    main()
