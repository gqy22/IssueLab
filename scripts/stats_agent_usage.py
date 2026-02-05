#!/usr/bin/env python3
"""
统计 GitHub Actions 中 Agent 的使用情况
收集: 运行轮数、工具调用次数、成本等

使用方法:
    uv run python scripts/stats_agent_usage.py

注意: 需要安装 gh CLI 并登录
"""

import asyncio
import json
import os
import re
import subprocess
import tempfile
from typing import Any
import sys


def run_cmd(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """执行 shell 命令"""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def get_workflow_runs(limit: int = 50) -> list[dict]:
    """获取最近的 workflow runs"""
    code, stdout, _ = run_cmd([
        "gh", "run", "list",
        "--limit", str(limit),
        "--json", "number,name,status,conclusion,startedAt,workflowName"
    ])
    if code != 0:
        print(f"Error getting runs: {stdout}")
        return []
    return json.loads(stdout)


def get_workflow_jobs(run_id: str) -> list[dict]:
    """获取 workflow run 的所有 jobs"""
    repo = os.getenv('GITHUB_REPOSITORY', 'gqy20/IssueLab')
    code, stdout, _ = run_cmd([
        "gh", "api",
        f"repos/{repo}/actions/runs/{run_id}/jobs",
        "--jq", "[.jobs[] | {name, id, status, conclusion}]"
    ])
    if code != 0:
        return []
    try:
        return json.loads(stdout)
    except:
        return []


def get_job_id_by_name(run_id: str, job_name: str) -> str:
    """根据 job 名称获取 job ID"""
    jobs = get_workflow_jobs(run_id)
    for job in jobs:
        if job.get("name") == job_name:
            return str(job.get("id", ""))
    return ""


def get_job_logs(run_id: str, job_name: str) -> str:
    """获取特定 job 的日志"""
    job_id = get_job_id_by_name(run_id, job_name)
    if not job_id:
        return ""

    # 使用 API 获取单个 job 的日志
    repo = os.getenv('GITHUB_REPOSITORY', 'gqy20/IssueLab')
    code, stdout, _ = run_cmd([
        "gh", "api",
        f"repos/{repo}/actions/runs/{run_id}/logs",
        "--jq", "."  # 直接获取原始响应
    ])
    if code != 0:
        return ""

    # 尝试查找特定 job 的日志
    try:
        logs_data = json.loads(stdout)
        # logs_data 是一个字典，key 是文件名
        for filename, content in logs_data.items():
            if job_name.lower() in filename.lower() or "agent" in filename.lower():
                return content
        # 如果没找到，返回第一个日志
        if logs_data:
            return list(logs_data.values())[0]
    except:
        pass

    return ""


def get_run_artifacts(run_id: str) -> list[dict]:
    """获取 run 的 artifacts"""
    repo = os.getenv('GITHUB_REPOSITORY', 'gqy20/IssueLab')
    code, stdout, _ = run_cmd([
        "gh", "api",
        f"repos/{repo}/actions/runs/{run_id}/artifacts",
        "--jq", "[.artifacts[] | {name, id}]"
    ])
    if code != 0:
        return []
    try:
        return json.loads(stdout)
    except:
        return []


def parse_usage_from_log(log: str) -> dict[str, Any]:
    """从日志中解析使用统计"""
    stats = {
        "runs_found": 0,
        "cost_usd": 0.0,
        "total_turns": 0,
        "total_tool_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "agents": {}
    }

    # 匹配 agent 统计信息模式（本地运行格式）
    # [observer] [Stats] 成本: $0.1671, 轮数: 2, 工具调用: 1
    local_pattern = r'\[(\w+)\] \[Stats\] 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+)'
    local_pattern_tokens = (
        r'\[(\w+)\] \[Stats\] 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+), '
        r'输入Token: (\d+), 输出Token: (\d+), 总Token: (\d+)'
    )

    # 匹配完成日志（本地运行格式）
    # [observer] 完成 - 响应长度: 1149 字符, 成本: $0.1671, 轮数: 2, 工具调用: 1
    local_complete_pattern = r'\[(\w+)\] 完成 - 响应长度: \d+ 字符, 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+)'
    local_complete_pattern_tokens = (
        r'\[(\w+)\] 完成 - 响应长度: \d+ 字符, 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+), '
        r'输入Token: (\d+), 输出Token: (\d+), 总Token: (\d+)'
    )

    # 匹配 GitHub Actions 格式（包含完整路径）
    # ... [executor.py:137] - [observer] [Stats] 成本: $0.1671, 轮数: 2, 工具调用: 1
    actions_pattern = r'\]\s*\[(\w+)\] \[Stats\] 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+)'
    actions_pattern_tokens = (
        r'\]\s*\[(\w+)\] \[Stats\] 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具调用: (\d+), '
        r'输入Token: (\d+), 输出Token: (\d+), 总Token: (\d+)'
    )

    # 匹配 Issue 完成日志
    # [Issue#1] observer 完成 - 成本: $0.1671, 轮数: 2, 工具: 1
    issue_pattern = r'\[Issue#\d+\] (\w+) 完成 - 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具: (\d+)'
    issue_pattern_tokens = (
        r'\[Issue#\d+\] (\w+) 完成 - 成本:\s*\$?([0-9.]+), 轮数: (\d+), 工具: (\d+), '
        r'输入Token: (\d+), 输出Token: (\d+), 总Token: (\d+)'
    )

    # 去重记录已处理的 agent，避免重复计算
    processed_agents = set()

    patterns = [
        (local_pattern_tokens, 7),
        (local_complete_pattern_tokens, 7),
        (actions_pattern_tokens, 7),
        (issue_pattern_tokens, 7),
        (local_pattern, 4),
        (local_complete_pattern, 4),
        (actions_pattern, 4),
        (issue_pattern, 4),
    ]

    for pattern, groups in patterns:
        matches = re.findall(pattern, log, re.IGNORECASE)
        for match in matches:
            if len(match) != groups:
                continue
            agent = match[0]
            cost = float(match[1])
            turns = int(match[2])
            tools = int(match[3])
            input_tokens = int(match[4]) if groups == 7 else 0
            output_tokens = int(match[5]) if groups == 7 else 0
            total_tokens = int(match[6]) if groups == 7 else 0

            if agent in processed_agents:
                continue
            processed_agents.add(agent)

            if agent not in stats["agents"]:
                stats["agents"][agent] = {
                    "runs": 0, "cost_usd": 0.0,
                    "total_turns": 0, "total_tool_calls": 0,
                    "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
                }

            stats["agents"][agent]["runs"] += 1
            stats["agents"][agent]["cost_usd"] += cost
            stats["agents"][agent]["total_turns"] += turns
            stats["agents"][agent]["total_tool_calls"] += tools
            stats["agents"][agent]["input_tokens"] += input_tokens
            stats["agents"][agent]["output_tokens"] += output_tokens
            stats["agents"][agent]["total_tokens"] += total_tokens

            stats["runs_found"] += 1
            stats["cost_usd"] += cost
            stats["total_turns"] += turns
            stats["total_tool_calls"] += tools
            stats["total_input_tokens"] += input_tokens
            stats["total_output_tokens"] += output_tokens
            stats["total_tokens"] += total_tokens

    return stats


def download_and_parse_artifacts(run_id: str) -> dict:
    """下载并解析 artifacts 中的日志"""
    stats = {
        "runs_found": 0,
        "cost_usd": 0.0,
        "total_turns": 0,
        "total_tool_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "agents": {}
    }

    artifacts = get_run_artifacts(run_id)
    if not artifacts:
        return stats

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = os.path.join(tmpdir, "artifacts")
        os.makedirs(artifact_dir, exist_ok=True)

        for artifact in artifacts:
            artifact_name = artifact.get("name", "")
            artifact_id = str(artifact.get("id", ""))

            # 只处理 agent 日志类型的 artifact
            if "log" not in artifact_name.lower():
                continue

            # 下载 artifact
            run_cmd(["gh", "run", "download", artifact_id, "--dir", artifact_dir])

            # 解析下载的文件
            for root, dirs, files in os.walk(artifact_dir):
                for filename in files:
                    if filename.endswith(".log"):
                        filepath = os.path.join(root, filename)
                        try:
                            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()

                            parsed = parse_usage_from_log(content)
                            stats["runs_found"] += parsed["runs_found"]
                            stats["cost_usd"] += parsed["cost_usd"]
                            stats["total_turns"] += parsed["total_turns"]
                            stats["total_tool_calls"] += parsed["total_tool_calls"]
                            stats["total_input_tokens"] += parsed.get("total_input_tokens", 0)
                            stats["total_output_tokens"] += parsed.get("total_output_tokens", 0)
                            stats["total_tokens"] += parsed.get("total_tokens", 0)

                            for agent, agent_stats in parsed["agents"].items():
                                if agent not in stats["agents"]:
                                    stats["agents"][agent] = {
                                        "runs": 0, "cost_usd": 0.0,
                                        "total_turns": 0, "total_tool_calls": 0,
                                        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
                                    }
                                for k, v in agent_stats.items():
                                    stats["agents"][agent][k] += v

                        except Exception as e:
                            print(f"  Warning: Failed to parse {filepath}: {e}")

    return stats


async def main():
    print("=" * 60)
    print("GitHub Actions Agent 使用统计")
    print("=" * 60)

    # 1. 获取最近的 workflow runs
    print("\n[1/3] 获取最近的 Workflow Runs...")
    runs = get_workflow_runs(50)
    print(f"     找到 {len(runs)} 个 runs")

    # 2. 分析日志中的使用统计
    print("\n[2/3] 分析 Agent 使用统计...")

    total_stats = {
        "runs_found": 0,
        "cost_usd": 0.0,
        "total_turns": 0,
        "total_tool_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "agents": {},
        "workflows_analyzed": 0,
        "artifacts_analyzed": 0
    }

    # 分析每个 run
    for run in runs:
        run_id = str(run["number"])
        run_name = run["name"]
        run_status = run["status"]

        # 只分析完成的 runs
        if run_status != "completed":
            continue

        # 首先尝试从 artifacts 解析
        artifact_stats = download_and_parse_artifacts(run_id)

        if artifact_stats["runs_found"] > 0:
            total_stats["workflows_analyzed"] += 1
            total_stats["artifacts_analyzed"] += 1
            total_stats["runs_found"] += artifact_stats["runs_found"]
            total_stats["cost_usd"] += artifact_stats["cost_usd"]
            total_stats["total_turns"] += artifact_stats["total_turns"]
            total_stats["total_tool_calls"] += artifact_stats["total_tool_calls"]
            total_stats["total_input_tokens"] += artifact_stats.get("total_input_tokens", 0)
            total_stats["total_output_tokens"] += artifact_stats.get("total_output_tokens", 0)
            total_stats["total_tokens"] += artifact_stats.get("total_tokens", 0)

            for agent, agent_stats in artifact_stats["agents"].items():
                if agent not in total_stats["agents"]:
                    total_stats["agents"][agent] = {
                        "runs": 0, "cost_usd": 0.0,
                        "total_turns": 0, "total_tool_calls": 0,
                        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
                    }
                for k, v in agent_stats.items():
                    total_stats["agents"][agent][k] += v

            print(f"  [{run_name} #{run_id}] +{artifact_stats['runs_found']} runs, ${artifact_stats['cost_usd']:.4f}")
            continue

        # 如果没有 artifact，从 job logs 解析
        jobs = get_workflow_jobs(run_id)
        run_has_stats = False

        for job in jobs:
            job_name = job.get("name", "")
            job_status = job.get("status", "")
            job_conclusion = job.get("conclusion", "")

            if job_status != "completed" or job_conclusion != "success":
                continue

            # 只分析 agent 相关的 jobs
            if not any(keyword in job_name.lower() for keyword in ["agent", "moderator", "reviewer", "observer", "summarizer"]):
                continue

            logs = get_job_logs(run_id, job_name)
            if not logs:
                continue

            parsed = parse_usage_from_log(logs)
            if parsed["runs_found"] > 0:
                run_has_stats = True
                total_stats["workflows_analyzed"] += 1

                for agent, agent_stats in parsed["agents"].items():
                    if agent not in total_stats["agents"]:
                        total_stats["agents"][agent] = {
                            "runs": 0, "cost_usd": 0.0,
                            "total_turns": 0, "total_tool_calls": 0,
                            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
                        }
                    for k, v in agent_stats.items():
                        total_stats["agents"][agent][k] += v

                total_stats["runs_found"] += parsed["runs_found"]
                total_stats["cost_usd"] += parsed["cost_usd"]
                total_stats["total_turns"] += parsed["total_turns"]
                total_stats["total_tool_calls"] += parsed["total_tool_calls"]
                total_stats["total_input_tokens"] += parsed.get("total_input_tokens", 0)
                total_stats["total_output_tokens"] += parsed.get("total_output_tokens", 0)
                total_stats["total_tokens"] += parsed.get("total_tokens", 0)

        if run_has_stats:
            print(f"  [{run_name} #{run_id}] 从日志解析完成")

    # 3. 输出统计结果
    print("\n[3/3] 统计结果:")
    print("-" * 60)

    print(f"\n分析时间范围: 最近 50 个 workflow runs")
    print(f"分析的工作流数: {total_stats['workflows_analyzed']}")
    print(f"解析的 artifacts 数: {total_stats['artifacts_analyzed']}")

    if total_stats["runs_found"] == 0:
        print("\n注意: 未找到 Agent 使用统计。")
        print("可能原因:")
        print("  1. GitHub Actions 日志默认不显示 DEBUG/INFO 级别日志")
        print("  2. 'Dispatch to User Agents' 工作流将任务分发到用户 fork")
        print("  3. Artifact 已过保留期 (默认 7 天)")
        print("\n获取完整统计的方法:")
        print("  - 在本地运行 agent: uv run python -m issuelab execute --issue 1 --agents observer")
        print("  - 在用户仓库中运行此脚本")
        print("  - 查看 Actions 页面中的 Debug 日志")

    print(f"\n总使用量 (当前仓库):")
    print(f"  - Agent 运行次数: {total_stats['runs_found']}")
    print(f"  - 总成本: ${total_stats['cost_usd']:.4f}")
    print(f"  - 总对话轮数: {total_stats['total_turns']}")
    print(f"  - 总工具调用次数: {total_stats['total_tool_calls']}")
    print(f"  - 输入Token: {total_stats['total_input_tokens']}")
    print(f"  - 输出Token: {total_stats['total_output_tokens']}")
    print(f"  - 总Token: {total_stats['total_tokens']}")

    if total_stats["agents"]:
        print(f"\n按 Agent 统计:")
        print(
            f"{'Agent':<20} {'运行次数':>8} {'成本(USD)':>12} {'轮数':>8} {'工具调用':>8} "
            f"{'输入Tok':>10} {'输出Tok':>10} {'总Tok':>10}"
        )
        print("-" * 60)

        for agent in sorted(total_stats["agents"].keys()):
            stats = total_stats["agents"][agent]
            print(
                f"{agent:<20} {stats['runs']:>8} ${stats['cost_usd']:>10.4f} {stats['total_turns']:>8} "
                f"{stats['total_tool_calls']:>8} {stats['input_tokens']:>10} {stats['output_tokens']:>10} "
                f"{stats['total_tokens']:>10}"
            )

    print("\n" + "=" * 60)

    # 保存结果到 JSON
    output_file = "/tmp/agent_usage_stats.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(total_stats, f, indent=2, ensure_ascii=False)
    print(f"\n详细结果已保存到: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())


def parse_local_input() -> dict:
    """从 stdin 解析本地运行日志"""
    log = sys.stdin.read()
    if not log:
        return {'runs_found': 0, 'cost_usd': 0.0, 'total_turns': 0, 'total_tool_calls': 0, 'total_input_tokens': 0, 'total_output_tokens': 0, 'total_tokens': 0, 'agents': {}}
    return parse_usage_from_log(log)


def print_stats(stats: dict):
    """打印统计结果"""
    print("=" * 60)
    print("Agent 使用统计结果")
    print("=" * 60)

    print(f"\n总使用量:")
    print(f"  - Agent 运行次数: {stats['runs_found']}")
    print(f"  - 总成本: ${stats['cost_usd']:.4f}")
    print(f"  - 总对话轮数: {stats['total_turns']}")
    print(f"  - 总工具调用次数: {stats['total_tool_calls']}")
    print(f"  - 输入Token: {stats.get('total_input_tokens', 0)}")
    print(f"  - 输出Token: {stats.get('total_output_tokens', 0)}")
    print(f"  - 总Token: {stats.get('total_tokens', 0)}")

    if stats['agents']:
        print(f"\n按 Agent 统计:")
        print(
            f"{'Agent':<20} {'运行次数':>8} {'成本(USD)':>12} {'轮数':>8} {'工具调用':>8} "
            f"{'输入Tok':>10} {'输出Tok':>10} {'总Tok':>10}"
        )
        print("-" * 60)

        for agent in sorted(stats['agents'].keys()):
            s = stats['agents'][agent]
            print(
                f"{agent:<20} {s['runs']:>8} ${s['cost_usd']:>10.4f} {s['total_turns']:>8} "
                f"{s['total_tool_calls']:>8} {s.get('input_tokens', 0):>10} {s.get('output_tokens', 0):>10} "
                f"{s.get('total_tokens', 0):>10}"
            )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--local':
        # 本地模式：从 stdin 读取
        stats = parse_local_input()
        print_stats(stats)
    else:
        asyncio.run(main())
