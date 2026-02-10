"""Shared helpers for CLI command handlers."""

import asyncio
import os

from issuelab.agents.executor import run_agents_parallel
from issuelab.tools.github import post_comment


def is_result_publishable(result: dict) -> tuple[bool, str]:
    if not bool(result.get("ok", True)):
        error_type = str(result.get("error_type") or "unknown")
        error_message = str(result.get("error_message") or "execution failed")
        return False, f"error_type={error_type}, error={error_message}"

    response = str(result.get("response") or "")
    if response.startswith("[错误]") or response.startswith("[系统护栏]"):
        return False, "response is an internal error payload"
    return True, ""


def build_failure_comment(agent_name: str, result: dict) -> str:
    failed_stage = str(result.get("failed_stage") or result.get("stage") or "unknown")
    error_type = str(result.get("error_type") or "unknown")
    error_message = str(result.get("error_message") or "execution failed")
    return (
        f"[Agent: {agent_name}]\n"
        "[系统护栏] 本次自动评审未产出可发布结论。\n"
        f"- failed_stage: {failed_stage}\n"
        f"- error_type: {error_type}\n"
        f"- error_message: {error_message}\n"
        "- 建议：修复工具/网络可用性后重试，避免基于不完整证据发布结论。"
    )


def should_post_failure_comment() -> bool:
    """Whether to post system failure details to issue."""
    return os.environ.get("ISSUELAB_POST_FAILURE_COMMENT", "0").lower() in {"1", "true", "yes", "on"}


def print_agent_result(agent_name: str, result: dict) -> str:
    response = result.get("response", str(result))
    cost_usd = result.get("cost_usd", 0.0)
    num_turns = result.get("num_turns", 0)
    tool_calls = len(result.get("tool_calls", []))

    print(f"\n=== {agent_name} result (成本: ${cost_usd:.4f}, 轮数: {num_turns}, 工具: {tool_calls}) ===")
    print(response)
    return str(response)


def maybe_post_agent_result(
    issue_number: int, agent_name: str, response: str, result: dict, repo: str | None = None
) -> bool | None:
    publishable, reason = is_result_publishable(result)
    if publishable:
        if post_comment(issue_number, response, agent_name=agent_name, repo=repo):
            if repo:
                print(f"[OK] 已发布到 {repo}#{issue_number}")
            else:
                print(f"[OK] {agent_name} response posted to issue #{issue_number}")
            return True
        if repo:
            print(f"[ERROR] 发布到 {repo}#{issue_number} 失败")
        else:
            print(f"[ERROR] Failed to post {agent_name} response")
        return False

    print(f"[WARN] {agent_name} result blocked by guardrail: {reason}")
    if should_post_failure_comment():
        body_to_post = build_failure_comment(agent_name, result)
        if post_comment(issue_number, body_to_post, agent_name=agent_name, repo=repo):
            if repo:
                print(f"[OK] 已发布失败摘要到 {repo}#{issue_number}")
            else:
                print(f"[OK] {agent_name} failure summary posted to issue #{issue_number}")
        else:
            if repo:
                print(f"[ERROR] 发布失败摘要到 {repo}#{issue_number} 失败")
            else:
                print(f"[ERROR] Failed to post {agent_name} failure summary")
    return None


def run_agents_command(
    issue_number: int,
    agents: list[str],
    context: str,
    comment_count: int,
    *,
    post: bool = False,
    repo: str | None = None,
    available_agents: list[dict] | None = None,
) -> dict:
    trigger_comment = os.environ.get("ISSUELAB_TRIGGER_COMMENT", "")
    results = asyncio.run(
        run_agents_parallel(
            issue_number,
            agents,
            context,
            comment_count,
            available_agents=available_agents,
            trigger_comment=trigger_comment,
        )
    )

    for agent_name, result in results.items():
        response = print_agent_result(agent_name, result)
        if post:
            maybe_post_agent_result(issue_number, agent_name, response, result, repo=repo)
    return results
