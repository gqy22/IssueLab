"""Personal agent command handlers."""

import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from issuelab.commands.common import maybe_post_agent_result, run_agents_command


def handle_personal_scan(args: Namespace) -> int | None:
    import yaml

    from issuelab.personal_scan import scan_issues_for_personal_agent

    agent_config_path = f"agents/{args.agent}/agent.yml"
    try:
        with open(agent_config_path) as f:
            agent_config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[ERROR] 未找到agent配置: {agent_config_path}", file=sys.stderr)
        return 1

    issue_numbers = [int(n.strip()) for n in args.issues.split(",") if n.strip().isdigit()]
    if not issue_numbers:
        print("[ERROR] 未提供有效的issue编号", file=sys.stderr)
        return 1

    result = scan_issues_for_personal_agent(
        agent_name=args.agent,
        agent_config=agent_config,
        issue_numbers=issue_numbers,
        repo=args.repo,
        max_replies=args.max_replies,
        username="",  # TODO: 从环境获取
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return None


def handle_personal_reply(args: Namespace) -> int | None:
    agent_config_path = f"agents/{args.agent}/agent.yml"
    if not Path(agent_config_path).exists():
        print(f"[ERROR] 未找到agent配置: {agent_config_path}")
        return 1

    if args.issue_title and args.issue_body:
        issue_title = args.issue_title
        issue_body = args.issue_body
        print("使用传入的Issue信息")
    else:
        try:
            result = subprocess.run(
                ["gh", "issue", "view", str(args.issue), "--repo", args.repo, "--json", "title,body"],
                capture_output=True,
                text=True,
                check=True,
            )
            issue_data = json.loads(result.stdout)
            issue_title = issue_data.get("title", "")
            issue_body = issue_data.get("body", "")
            print("从主仓库获取Issue信息")
        except Exception as e:
            print(f"[ERROR] 获取issue信息失败: {e}")
            return 1

    context = f"""你被邀请参与 GitHub Issue #{args.issue} 的讨论。

**Issue 标题**: {issue_title}

**Issue 内容**:
{issue_body}

**你的任务**:
基于你的专业知识和经验，对这个Issue提供有价值的见解、建议或评审意见。

**回复要求**:
1. 直接针对Issue的具体内容发表观点
2. 提供建设性的建议或可行的解决方案
3. 如相关可分享类似案例或最佳实践
4. 保持专业、友好、简洁的语气

请直接给出你的专业回复，不需要任何前缀或说明。"""

    available_agents = None
    if hasattr(args, "available_agents") and args.available_agents:
        try:
            available_agents = json.loads(args.available_agents)
            print(f"[INFO] 收到 {len(available_agents)} 个可用智能体信息")
        except json.JSONDecodeError as e:
            print(f"[WARNING] 解析available_agents失败: {e}")

    print(f"[START] 使用 {args.agent} 分析 {args.repo}#{args.issue}")
    results = run_agents_command(
        args.issue,
        [args.agent],
        context,
        0,
        post=False,
        repo=args.repo,
        available_agents=available_agents,
    )

    if args.agent not in results:
        print(f"[ERROR] Agent {args.agent} 执行失败")
        return 1

    result = results[args.agent]
    response = result.get("response", str(result))

    if getattr(args, "post", False):
        posted = maybe_post_agent_result(args.issue, args.agent, response, result, repo=args.repo)
        if posted is False:
            output_file = os.environ.get("GITHUB_OUTPUT")
            if output_file:
                try:
                    with open(output_file, "a") as f:
                        escaped_response = response.replace("\n", "%0A").replace("\r", "%0D")
                        f.write(f"agent_response={escaped_response}\n")
                        f.write("comment_failed=true\n")
                    print("[INFO] 结果已保存到 GITHUB_OUTPUT，workflow可以处理")
                except Exception as e:
                    print(f"[WARNING] 保存到 GITHUB_OUTPUT 失败: {e}")

    return None
