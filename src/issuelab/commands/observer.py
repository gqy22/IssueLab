"""Observer command handlers."""

from argparse import Namespace

from issuelab.agents.observer import run_observer
from issuelab.tools import github as github_tools
from issuelab.tools.github import get_issue_info, post_comment


def handle_observe(args: Namespace, issue_info: dict, issue_file: str, comments: str) -> None:
    issue_body_ref = (
        f"内容已保存至文件: {issue_file}\n请使用 Read 工具读取该文件后再分析。"
        if issue_file
        else (issue_info.get("body", "") or "无内容")
    )
    comments_ref = "历史评论已包含在同一文件中。" if issue_file else (comments or "无评论")

    import asyncio

    result = asyncio.run(run_observer(args.issue, issue_info.get("title", ""), issue_body_ref, comments_ref))

    print(f"\n=== Observer Analysis for Issue #{args.issue} ===")
    print(f"\nAnalysis:\n{result.get('analysis', 'N/A')}")
    print(f"\nShould Trigger: {result.get('should_trigger', False)}")
    if result.get("should_trigger"):
        print(f"Agent: {result.get('agent', 'N/A')}")
        print(f"Trigger Comment: {result.get('comment', 'N/A')}")
        print(f"Reason: {result.get('reason', 'N/A')}")

        if getattr(args, "post", False):
            if result.get("comment") and post_comment(args.issue, result["comment"], agent_name="observer"):
                print(f"\n[OK] Trigger comment posted to issue #{args.issue}")
            else:
                print("\n[ERROR] Failed to post trigger comment")
    else:
        print(f"Skip Reason: {result.get('reason', 'N/A')}")


def handle_observe_batch(args: Namespace) -> None:
    import asyncio

    from issuelab.agents.observer import run_observer_batch

    issue_numbers = [int(i.strip()) for i in args.issues.split(",") if i.strip()]
    if not issue_numbers:
        print("[ERROR] 未提供有效的 Issue 编号")
        return

    print(f"\n=== 并行分析 {len(issue_numbers)} 个 Issues ===")

    issue_data_list = []
    for issue_num in issue_numbers:
        try:
            data = get_issue_info(issue_num, format_comments=True)
            issue_file = github_tools.write_issue_context_file(
                issue_number=issue_num,
                title=data.get("title", ""),
                body=data.get("body", ""),
                comments=data.get("comments", ""),
                comment_count=data.get("comment_count", 0),
            )

            issue_data_list.append(
                {
                    "issue_number": issue_num,
                    "issue_title": data.get("title", ""),
                    "issue_body": f"内容已保存至文件: {issue_file}\n请使用 Read 工具读取该文件后再分析。",
                    "comments": "历史评论已包含在同一文件中。",
                }
            )
        except Exception as e:
            print(f"[WARNING] 获取 Issue #{issue_num} 失败: {e}")
            continue

    if not issue_data_list:
        print("[ERROR] 无有效的 Issue 数据")
        return

    results = asyncio.run(run_observer_batch(issue_data_list, max_parallel=args.max_parallel))

    print(f"\n{'=' * 60}")
    print(f"分析完成：{len(results)} 个 Issues")
    print(f"{'=' * 60}\n")

    triggered_count = 0
    for result in results:
        issue_num = result.get("issue_number")
        should_trigger = result.get("should_trigger", False)

        print(f"Issue #{issue_num}:")
        print(f"  触发: {'[OK] 是' if should_trigger else '[ERROR] 否'}")

        if should_trigger:
            triggered_count += 1
            print(f"  Agent: {result.get('agent', 'N/A')}")
            print(f"  理由: {result.get('reason', 'N/A')}")

            if getattr(args, "auto_trigger", False):
                from issuelab.observer_trigger import auto_trigger_agent

                issue_info = next((d for d in issue_data_list if d["issue_number"] == issue_num), None)
                if issue_info:
                    success = auto_trigger_agent(
                        agent_name=result.get("agent", ""),
                        issue_number=issue_num,
                        issue_title=issue_info.get("issue_title", ""),
                        issue_body=issue_info.get("issue_body", ""),
                    )
                    if success:
                        print("  [OK] 已自动触发 agent")
                    else:
                        print("  [ERROR] 自动触发失败")
        else:
            print(f"  原因: {result.get('reason', 'N/A')}")

        if "error" in result:
            print(f"  [WARNING] 错误: {result['error']}")
        print()

    print(f"\n总结: {triggered_count}/{len(results)} 个 Issues 需要触发 Agent")
