#!/usr/bin/env python3
"""Generate daily Issue/Actions facts and a baseline markdown report.

Usage:
  python scripts/daily_issue_health_report.py --repo owner/repo --hours 24 --output /tmp/report.md --facts-output /tmp/facts.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _run_gh_json(args: list[str]) -> Any:
    cmd = ["gh", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh command failed: {' '.join(cmd)}\n{proc.stderr}")
    return json.loads(proc.stdout)


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _gh_api(path: str) -> Any:
    return _run_gh_json(["api", path])


def _list_recent_issue_objects(repo: str, since_iso: str) -> list[dict[str, Any]]:
    path = f"repos/{repo}/issues?state=all&sort=updated&direction=desc&since={since_iso}&per_page=100"
    raw = _gh_api(path)
    return [item for item in raw if "pull_request" not in item]


def _list_issue_comments(repo: str, issue_number: int) -> list[dict[str, Any]]:
    path = f"repos/{repo}/issues/{issue_number}/comments?per_page=100"
    return _gh_api(path)


def _list_workflow_runs(repo: str) -> list[dict[str, Any]]:
    path = f"repos/{repo}/actions/runs?per_page=100"
    raw = _gh_api(path)
    return raw.get("workflow_runs", [])


def _list_failed_jobs_for_run(repo: str, run_id: int) -> list[dict[str, str]]:
    path = f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    raw = _gh_api(path)
    jobs = raw.get("jobs", [])
    failed: list[dict[str, str]] = []
    for job in jobs:
        if str(job.get("conclusion", "")) != "failure":
            continue
        failed_steps: list[str] = []
        for step in job.get("steps", []) or []:
            if str((step or {}).get("conclusion", "")) == "failure":
                name = str((step or {}).get("name", "")).strip()
                if name:
                    failed_steps.append(name)
        failed.append(
            {
                "job_name": str(job.get("name", "")),
                "runner_name": str(job.get("runner_name", "")),
                "url": str(job.get("html_url", "")),
                "failed_steps": ", ".join(failed_steps[:5]),
            }
        )
    return failed[:8]


def _list_open_issues(repo: str) -> list[dict[str, Any]]:
    path = f"repos/{repo}/issues?state=open&sort=updated&direction=desc&per_page=100"
    raw = _gh_api(path)
    return [item for item in raw if "pull_request" not in item]


@dataclass
class DailySummary:
    since_iso: str
    now_iso: str
    new_issues: int
    touched_issues: int
    comments_today: int
    participants: int
    agent_error_comments: int
    top_issues: list[tuple[int, int, str]]
    workflow_total: int
    workflow_failed: int
    workflow_cancelled: int
    workflow_fail_by_name: list[tuple[str, int, int]]
    failed_runs: list[dict[str, Any]]
    open_problem_issues: list[tuple[int, str, str]]
    hot_open_issues: list[tuple[int, int, str]]
    error_comment_examples: list[dict[str, str]]


def _trim_text(text: str, max_len: int = 220) -> str:
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def build_summary(repo: str, since: datetime, now: datetime) -> DailySummary:
    since_iso = since.isoformat().replace("+00:00", "Z")
    now_iso = now.isoformat().replace("+00:00", "Z")

    issues = _list_recent_issue_objects(repo, since_iso)
    touched_issues = len(issues)
    new_issues = sum(1 for i in issues if _iso_to_dt(i["created_at"]) >= since)

    comments_today = 0
    participants: set[str] = set()
    issue_comment_counter: Counter[int] = Counter()
    issue_title_map: dict[int, str] = {}
    error_pattern = re.compile(
        r"\[系统护栏\]|\[错误\]|execution failed|dispatch report|failed to dispatch|error_type|failed_stage",
        re.IGNORECASE,
    )
    agent_error_comments = 0
    error_comment_examples: list[dict[str, str]] = []

    for issue in issues:
        issue_number = int(issue["number"])
        issue_title_map[issue_number] = str(issue.get("title", ""))
        user = (issue.get("user") or {}).get("login")
        if user:
            participants.add(str(user))

        for c in _list_issue_comments(repo, issue_number):
            created = _iso_to_dt(str(c.get("created_at", "")))
            if created < since or created > now:
                continue
            comments_today += 1
            issue_comment_counter[issue_number] += 1
            author = (c.get("user") or {}).get("login")
            if author:
                participants.add(str(author))
            body = str(c.get("body", ""))
            if error_pattern.search(body):
                agent_error_comments += 1
                if len(error_comment_examples) < 10:
                    error_comment_examples.append(
                        {
                            "issue_number": str(issue_number),
                            "issue_title": issue_title_map.get(issue_number, ""),
                            "url": str(c.get("html_url", "")),
                            "author": str((c.get("user") or {}).get("login", "")),
                            "created_at": str(c.get("created_at", "")),
                            "excerpt": _trim_text(body, 260),
                        }
                    )

    top_issues: list[tuple[int, int, str]] = []
    for issue_no, count in issue_comment_counter.most_common(5):
        top_issues.append((issue_no, count, issue_title_map.get(issue_no, "")))

    runs = _list_workflow_runs(repo)
    recent_runs = [r for r in runs if _iso_to_dt(str(r.get("created_at", ""))) >= since]
    workflow_total = len(recent_runs)
    workflow_failed = sum(1 for r in recent_runs if r.get("conclusion") == "failure")
    workflow_cancelled = sum(1 for r in recent_runs if r.get("conclusion") == "cancelled")

    fail_by_name: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for run in recent_runs:
        name = str(run.get("name", "Unknown"))
        failed, total = fail_by_name[name]
        total += 1
        if run.get("conclusion") == "failure":
            failed += 1
        fail_by_name[name] = (failed, total)

    workflow_fail_by_name = sorted(
        [(name, ft[0], ft[1]) for name, ft in fail_by_name.items() if ft[0] > 0],
        key=lambda x: (-x[1], x[0]),
    )[:8]
    failed_runs: list[dict[str, Any]] = []
    for run in recent_runs:
        if run.get("conclusion") != "failure":
            continue
        run_id = int(run.get("id", 0) or 0)
        failed_jobs: list[dict[str, str]] = []
        # 控制 API 成本：仅拉取最近 12 个失败 run 的 job 级详情
        if run_id > 0 and len(failed_runs) < 12:
            try:
                failed_jobs = _list_failed_jobs_for_run(repo, run_id)
            except Exception:
                failed_jobs = []
        failed_runs.append(
            {
                "id": run_id,
                "name": str(run.get("name", "")),
                "event": str(run.get("event", "")),
                "created_at": str(run.get("created_at", "")),
                "updated_at": str(run.get("updated_at", "")),
                "url": str(run.get("html_url", "")),
                "head_branch": str(run.get("head_branch", "")),
                "status": str(run.get("status", "")),
                "conclusion": str(run.get("conclusion", "")),
                "failed_jobs": failed_jobs,
            }
        )
    failed_runs = failed_runs[:30]

    open_issues = _list_open_issues(repo)
    problem_keywords = re.compile(r"bug|error|fail|问题|故障|异常|报错|稳定性", re.IGNORECASE)
    open_problem_issues: list[tuple[int, str, str]] = []
    hot_open_issues: list[tuple[int, int, str]] = []
    for item in open_issues:
        number = int(item["number"])
        title = str(item.get("title", ""))
        url = str(item.get("html_url", ""))
        body = str(item.get("body", ""))
        labels = [str((lb or {}).get("name", "")) for lb in item.get("labels", [])]
        label_text = ",".join(labels)
        if problem_keywords.search(title) or problem_keywords.search(body) or "bug" in label_text.lower():
            open_problem_issues.append((number, title, url))
        comments_count = int(item.get("comments", 0))
        if comments_count >= 50:
            hot_open_issues.append((number, comments_count, title))

    return DailySummary(
        since_iso=since_iso,
        now_iso=now_iso,
        new_issues=new_issues,
        touched_issues=touched_issues,
        comments_today=comments_today,
        participants=len(participants),
        agent_error_comments=agent_error_comments,
        top_issues=top_issues,
        workflow_total=workflow_total,
        workflow_failed=workflow_failed,
        workflow_cancelled=workflow_cancelled,
        workflow_fail_by_name=workflow_fail_by_name,
        failed_runs=failed_runs,
        open_problem_issues=open_problem_issues[:10],
        hot_open_issues=hot_open_issues[:10],
        error_comment_examples=error_comment_examples,
    )


def build_facts_payload(repo: str, summary: DailySummary) -> dict[str, Any]:
    fail_rate = 0.0
    if summary.workflow_total > 0:
        fail_rate = summary.workflow_failed / summary.workflow_total * 100.0

    return {
        "repo": repo,
        "window": {
            "since": summary.since_iso,
            "until": summary.now_iso,
        },
        "metrics": {
            "new_issues": summary.new_issues,
            "touched_issues": summary.touched_issues,
            "comments_today": summary.comments_today,
            "participants": summary.participants,
            "agent_error_comments": summary.agent_error_comments,
            "workflow_total": summary.workflow_total,
            "workflow_failed": summary.workflow_failed,
            "workflow_cancelled": summary.workflow_cancelled,
            "workflow_fail_rate_pct": round(fail_rate, 2),
        },
        "top_issues": [
            {"issue_number": num, "new_comments": count, "title": title} for num, count, title in summary.top_issues
        ],
        "workflow_failure_by_name": [
            {"name": name, "failed": failed, "total": total} for name, failed, total in summary.workflow_fail_by_name
        ],
        "failed_runs": summary.failed_runs,
        "open_problem_issues": [
            {"issue_number": num, "title": title, "url": url} for num, title, url in summary.open_problem_issues
        ],
        "hot_open_issues": [
            {"issue_number": num, "comments": comments, "title": title}
            for num, comments, title in summary.hot_open_issues
        ],
        "error_comment_examples": summary.error_comment_examples,
    }


def render_markdown(repo: str, summary: DailySummary) -> str:
    lines: list[str] = []
    lines.append("# IssueLab 日报（自动生成）")
    lines.append("")
    lines.append(f"- 仓库: `{repo}`")
    lines.append(f"- 统计窗口: `{summary.since_iso}` ~ `{summary.now_iso}`")
    lines.append("")
    lines.append("## 今日问答概况")
    lines.append(f"- 新建 Issue: **{summary.new_issues}**")
    lines.append(f"- 有活动 Issue: **{summary.touched_issues}**")
    lines.append(f"- 新增评论: **{summary.comments_today}**")
    lines.append(f"- 参与人数（去重）: **{summary.participants}**")
    lines.append("")
    lines.append("## 稳定性评估")
    fail_rate = 0.0
    if summary.workflow_total > 0:
        fail_rate = summary.workflow_failed / summary.workflow_total * 100.0
    lines.append(f"- Actions 运行总数: **{summary.workflow_total}**")
    lines.append(f"- 失败: **{summary.workflow_failed}**，取消: **{summary.workflow_cancelled}**")
    lines.append(f"- 失败率: **{fail_rate:.1f}%**")
    lines.append(f"- Issue 评论中的系统错误痕迹: **{summary.agent_error_comments}**")
    lines.append("")

    lines.append("## 主要问题")
    if summary.workflow_fail_by_name:
        for name, failed, total in summary.workflow_fail_by_name:
            lines.append(f"- `{name}`: {failed}/{total} 失败")
    else:
        lines.append("- 今日未发现 workflow 失败")
    lines.append("")

    lines.append("## 热点问答")
    if summary.top_issues:
        for issue_no, count, title in summary.top_issues:
            lines.append(f"- #{issue_no}（{count} 条新评论） {title}")
    else:
        lines.append("- 今日暂无活跃问答")
    lines.append("")

    lines.append("## 待解决问题清单")
    if summary.open_problem_issues:
        for issue_no, title, url in summary.open_problem_issues:
            lines.append(f"- [ ] #{issue_no} {title} ({url})")
    else:
        lines.append("- [ ] 暂无显著问题 issue")
    if summary.hot_open_issues:
        for issue_no, comments_count, title in summary.hot_open_issues:
            lines.append(f"- [ ] 关注高讨论量 Issue: #{issue_no}（{comments_count} 评论） {title}")
    lines.append("")

    lines.append("---")
    lines.append("_由 Daily Issue Health Report 自动生成_")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily issue health report")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours")
    parser.add_argument("--output", required=True, help="Output markdown file")
    parser.add_argument("--facts-output", default="", help="Optional output path for JSON facts payload")
    args = parser.parse_args()

    now = datetime.now(UTC)
    since = now - timedelta(hours=max(1, args.hours))
    summary = build_summary(args.repo, since=since, now=now)
    markdown = render_markdown(args.repo, summary)
    facts = build_facts_payload(args.repo, summary)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"report generated: {output}")

    if args.facts_output:
        facts_out = Path(args.facts_output)
        facts_out.parent.mkdir(parents=True, exist_ok=True)
        facts_out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"facts generated: {facts_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
