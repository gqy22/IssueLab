"""Core command handlers: execute/review/list-agents."""

from argparse import Namespace
from collections.abc import Callable

from issuelab.agents.discovery import discover_agents, get_agent_matrix_markdown
from issuelab.commands.common import run_agents_command


def handle_execute(
    args: Namespace, context: str, comment_count: int, parse_agents_arg: Callable[[str], list[str]]
) -> int | None:
    agents = parse_agents_arg(args.agents)
    if not agents:
        print("[ERROR] 未提供有效的 agent 名称")
        return 1

    print(f"[START] 执行 agents: {agents}")
    run_agents_command(args.issue, agents, context, comment_count, post=getattr(args, "post", False))
    return None


def handle_review(args: Namespace, context: str, comment_count: int) -> None:
    agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
    results = run_agents_command(args.issue, agents, context, comment_count, post=getattr(args, "post", False))

    for agent_name, result in results.items():
        response = str(result.get("response", str(result)))
        if agent_name == "summarizer":
            from issuelab.response_processor import close_issue, should_auto_close

            if should_auto_close(response, agent_name):
                print(f"\n[INFO] 检测到 [CLOSE] 标记，正在自动关闭 Issue #{args.issue}...")
                if close_issue(args.issue):
                    print(f"[OK] Issue #{args.issue} 已自动关闭")
                else:
                    print("[ERROR] 自动关闭失败")


def handle_list_agents() -> None:
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
