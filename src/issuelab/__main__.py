"""主入口：支持多种子命令"""

import argparse
import asyncio
import json
import subprocess

from issuelab.config import Config
from issuelab.logging_config import get_logger, setup_logging
from issuelab.sdk_executor import (
    discover_agents,
    get_agent_matrix_markdown,
    run_agents_parallel,
    run_observer,
)
from issuelab.tools.github import get_issue_info, post_comment

# 初始化日志
setup_logging(level=Config.get_log_level(), log_file=Config.get_log_file())
logger = get_logger(__name__)


def parse_agents_arg(agents_str: str) -> list[str]:
    """
    解析 agents 参数，支持多种格式

    Args:
        agents_str: agents 字符串，支持:
            - 逗号分隔: "echo,test"
            - 空格分隔: "echo test"
            - JSON 数组: '["echo", "test"]'

    Returns:
        agent 名称列表（小写）
    """
    agents_str = agents_str.strip()

    # JSON 数组格式
    if agents_str.startswith("[") and agents_str.endswith("]"):
        try:
            agents = json.loads(agents_str)
            return [agent.lower() for agent in agents]
        except json.JSONDecodeError:
            logger.warning(f"JSON 格式解析失败，尝试其他格式: {agents_str}")

    # 逗号分隔格式（优先）
    if "," in agents_str:
        return [a.strip().lower() for a in agents_str.split(",") if a.strip()]

    # 空格分隔格式
    return [a.lower() for a in agents_str.split() if a]


def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # @mention 并行执行（简化版）
    execute_parser = subparsers.add_parser("execute", help="并行执行代理")
    execute_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    execute_parser.add_argument("--agents", type=str, required=True, help="代理名称（逗号分隔）")
    execute_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    # 顺序评审流程（简化版）
    review_parser = subparsers.add_parser("review", help="运行顺序评审流程")
    review_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    review_parser.add_argument("--post", action="store_true", help="自动发布结果到 Issue")

    # Observer 监控命令（简化版）
    observe_parser = subparsers.add_parser("observe", help="运行 Observer Agent 分析 Issue")
    observe_parser.add_argument("--issue", type=int, required=True, help="Issue 编号")
    observe_parser.add_argument("--post", action="store_true", help="自动发布触发评论到 Issue")

    # Observer 批量分析命令（并行）
    observe_batch_parser = subparsers.add_parser("observe-batch", help="并行分析多个 Issues")
    observe_batch_parser.add_argument("--issues", type=str, required=True, help="Issue 编号列表（逗号分隔）")
    observe_batch_parser.add_argument("--post", action="store_true", help="自动发布触发评论到 Issue")

    # 列出所有可用 Agent
    subparsers.add_parser("list-agents", help="列出所有可用的 Agent")

    args = parser.parse_args()

    # 自动获取 Issue 信息（适用于 execute, review, observe）
    if args.command in ("execute", "review", "observe"):
        print(f"📥 正在获取 Issue #{args.issue} 信息...")
        issue_info = get_issue_info(args.issue, format_comments=True)

        # 构建上下文
        context = f"**Issue 标题**: {issue_info['title']}\n\n**Issue 内容**:\n{issue_info['body']}"
        comment_count = issue_info["comment_count"]
        comments = issue_info["comments"]

        if comment_count > 0 and comments:
            context += f"\n\n**本 Issue 共有 {comment_count} 条历史评论，请仔细阅读并分析：**\n\n{comments}"

        print(f"✅ 已获取: 标题={issue_info['title'][:30]}..., 评论数={comment_count}")
    else:
        context = ""
        comment_count = 0
        comments = ""
        issue_info = {}

    if args.command == "execute":
        agents = parse_agents_arg(args.agents)

        if not agents:
            print("❌ 未提供有效的 agent 名称")
            return 1

        print(f"🚀 执行 agents: {agents}")

        results = asyncio.run(run_agents_parallel(args.issue, agents, context, comment_count))

        # 输出结果
        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
            print(response)

            # 如果需要，自动发布到 Issue
            if getattr(args, "post", False):
                if post_comment(args.issue, response):
                    print(f"✅ {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"❌ Failed to post {agent_name} response")

    elif args.command == "review":
        # 顺序执行：moderator -> reviewer_a -> reviewer_b -> summarizer
        agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
        results = asyncio.run(run_agents_parallel(args.issue, agents, context, comment_count))

        for agent_name, result in results.items():
            response = result.get("response", str(result))
            cost_usd = result.get("cost_usd", 0.0)
            num_turns = result.get("num_turns", 0)
            tool_calls = len(result.get("tool_calls", []))

            print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
            print(response)

            # 如果需要，自动发布到 Issue
            if getattr(args, "post", False):
                if post_comment(args.issue, response):
                    print(f"✅ {agent_name} response posted to issue #{args.issue}")
                else:
                    print(f"❌ Failed to post {agent_name} response")

    elif args.command == "observe":
        # 运行 Observer Agent 分析 Issue
        result = asyncio.run(
            run_observer(args.issue, issue_info.get("title", ""), issue_info.get("body", ""), comments)
        )

        print(f"\n=== Observer Analysis for Issue #{args.issue} ===")
        print(f"\nAnalysis:\n{result.get('analysis', 'N/A')}")
        print(f"\nShould Trigger: {result.get('should_trigger', False)}")
        if result.get("should_trigger"):
            print(f"Agent: {result.get('agent', 'N/A')}")
            print(f"Trigger Comment: {result.get('comment', 'N/A')}")
            print(f"Reason: {result.get('reason', 'N/A')}")

            # 如果需要，自动发布触发评论
            if getattr(args, "post", False):
                if result.get("comment") and post_comment(args.issue, result["comment"]):
                    print(f"\n✅ Trigger comment posted to issue #{args.issue}")
                else:
                    print("\n❌ Failed to post trigger comment")
        else:
            print(f"Skip Reason: {result.get('reason', 'N/A')}")

    elif args.command == "observe-batch":
        # 并行分析多个 Issues
        issue_numbers = [int(i.strip()) for i in args.issues.split(",") if i.strip()]

        if not issue_numbers:
            print("❌ 未提供有效的 Issue 编号")
            return

        print(f"\n=== 并行分析 {len(issue_numbers)} 个 Issues ===")

        # 获取所有 Issues 的详情
        issue_data_list = []
        for issue_num in issue_numbers:
            try:
                # 使用 gh 命令获取 Issue 详情
                result = subprocess.run(
                    ["gh", "issue", "view", str(issue_num), "--json", "title,body,comments"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                import json

                data = json.loads(result.stdout)

                # 格式化评论
                comments = []
                for comment in data.get("comments", []):
                    author = comment.get("author", {}).get("login", "unknown")
                    body = comment.get("body", "")
                    comments.append(f"- **[{author}]**: {body}")

                issue_data_list.append(
                    {
                        "issue_number": issue_num,
                        "issue_title": data.get("title", ""),
                        "issue_body": data.get("body", ""),
                        "comments": "\n".join(comments),
                    }
                )
            except Exception as e:
                print(f"⚠️  获取 Issue #{issue_num} 失败: {e}")
                continue

        if not issue_data_list:
            print("❌ 无有效的 Issue 数据")
            return

        # 并行分析
        from issuelab.sdk_executor import run_observer_batch

        results = asyncio.run(run_observer_batch(issue_data_list))

        # 输出结果
        print(f"\n{'=' * 60}")
        print(f"分析完成：{len(results)} 个 Issues")
        print(f"{'=' * 60}\n")

        triggered_count = 0
        for result in results:
            issue_num = result.get("issue_number")
            should_trigger = result.get("should_trigger", False)

            print(f"Issue #{issue_num}:")
            print(f"  触发: {'✅ 是' if should_trigger else '❌ 否'}")

            if should_trigger:
                triggered_count += 1
                print(f"  Agent: {result.get('agent', 'N/A')}")
                print(f"  理由: {result.get('reason', 'N/A')}")

                # 如果需要，自动发布触发评论
                if getattr(args, "post", False):
                    comment = result.get("comment")
                    if comment and post_comment(issue_num, comment):
                        print("  ✅ 已发布触发评论")
                    else:
                        print("  ❌ 发布评论失败")
            else:
                print(f"  原因: {result.get('reason', 'N/A')}")

            if "error" in result:
                print(f"  ⚠️  错误: {result['error']}")

            print()

        print(f"\n总结: {triggered_count}/{len(results)} 个 Issues 需要触发 Agent")

    elif args.command == "list-agents":
        # 列出所有可用的 Agent
        agents = discover_agents()
        print("\n=== Available Agents ===\n")
        print(f"{'Agent':<15} {'Description':<50} {'Trigger Conditions'}")
        print("-" * 100)
        for name, config in agents.items():
            conditions = config.get("trigger_conditions", [])
            if conditions and all(isinstance(c, str) for c in conditions):
                conditions_str = ", ".join(conditions)
            else:
                conditions_str = "auto-detect"
            desc = config.get("description", "")[:48]
            print(f"{name:<15} {desc:<50} {conditions_str[:40]}")

        print("\n\n=== Agent Matrix (for Observer) ===\n")
        print(get_agent_matrix_markdown())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
