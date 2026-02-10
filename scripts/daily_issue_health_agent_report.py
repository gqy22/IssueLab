#!/usr/bin/env python3
"""Generate an ops-agent daily diagnosis from facts payload."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import yaml

from issuelab.agents.discovery import load_prompt
from issuelab.agents.executor import run_single_agent
from issuelab.utils.yaml_text import extract_yaml_block


def _parse_structured_output(text: str) -> dict[str, Any] | None:
    yaml_text = extract_yaml_block(text)
    try:
        # 兼容裸 YAML（无 ```yaml fence）
        parsed = yaml.safe_load(yaml_text) if yaml_text else yaml.safe_load(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _has_evidence_links(structured: dict[str, Any] | None) -> bool:
    if not structured or not isinstance(structured, dict):
        return False
    links = structured.get("evidence_links", [])
    if isinstance(links, list):
        return any(isinstance(i, str) and i.startswith(("http://", "https://")) for i in links)
    return False


def _collect_evidence_links(facts: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for run in facts.get("failed_runs", []) or []:
        if isinstance(run, dict):
            url = str(run.get("url", "")).strip()
            if url and url not in links:
                links.append(url)
    for issue in facts.get("open_problem_issues", []) or []:
        if isinstance(issue, dict):
            url = str(issue.get("url", "")).strip()
            if url and url not in links:
                links.append(url)
    for c in facts.get("error_comment_examples", []) or []:
        if isinstance(c, dict):
            url = str(c.get("url", "")).strip()
            if url and url not in links:
                links.append(url)
    return links


def _build_ops_prompt(facts: dict[str, Any], max_links: int = 80) -> str:
    evidence_links = _collect_evidence_links(facts)[:max_links]
    facts_json = json.dumps(facts, ensure_ascii=False, indent=2)
    links_text = "\n".join(f"- {u}" for u in evidence_links) if evidence_links else "- (none)"
    return f"""
你是 IssueLab 的系统稳定性智能体（ops_daily）。
你的任务是基于“已给定证据”输出可执行的稳定性诊断，不允许编造不存在的事实。

分析约束：
- 只能使用输入 facts 与证据链接做判断
- 若证据不足，必须明确写出 uncertainty，不得强行下结论
- action_items 必须是可执行项，且每项包含 owner_type 和 due

输入 facts(JSON):
```json
{facts_json}
```

可引用证据链接：
{links_text}

请输出 YAML（若失败再降级为 Markdown）：
```yaml
summary: ""
overall_health: "green|yellow|red"
health_score: 0
root_causes:
  - issue: ""
    impact: "low|medium|high"
    evidence_links:
      - ""
risk_forecast_7d:
  - risk: ""
    probability: "low|medium|high"
    mitigation: ""
action_items:
  - title: ""
    owner_type: "workflow|config|prompt|code|ops"
    priority: "P0|P1|P2"
    due: "YYYY-MM-DD"
    expected_outcome: ""
uncertainties:
  - ""
evidence_links:
  - ""
confidence: "low|medium|high"
```
""".strip()


def _render_markdown(raw_response: str, structured: dict[str, Any] | None) -> str:
    lines: list[str] = []
    lines.append("## 系统智能体诊断（ops_daily）")
    lines.append("")
    if structured:
        lines.append(f"- overall_health: **{structured.get('overall_health', 'unknown')}**")
        lines.append(f"- health_score: **{structured.get('health_score', 'N/A')}**")
        lines.append(f"- confidence: **{structured.get('confidence', 'N/A')}**")
        lines.append("")

        lines.append("### 诊断摘要")
        lines.append(str(structured.get("summary", "（未提供）")))
        lines.append("")

        lines.append("### 根因")
        roots = structured.get("root_causes", [])
        if isinstance(roots, list) and roots:
            for item in roots:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('issue', '')}（impact: {item.get('impact', 'unknown')}）")
        else:
            lines.append("- （无）")
        lines.append("")

        lines.append("### 7天风险预测")
        risks = structured.get("risk_forecast_7d", [])
        if isinstance(risks, list) and risks:
            for item in risks:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('risk', '')}（probability: {item.get('probability', 'unknown')}）")
        else:
            lines.append("- （无）")
        lines.append("")

        lines.append("### 行动项")
        actions = structured.get("action_items", [])
        if isinstance(actions, list) and actions:
            for item in actions:
                if isinstance(item, dict):
                    lines.append(
                        "- [ ] "
                        + f"{item.get('title', '')} | {item.get('priority', 'P2')} | "
                        + f"{item.get('owner_type', 'ops')} | due {item.get('due', 'TBD')}"
                    )
        else:
            lines.append("- [ ] （无）")
        lines.append("")

        lines.append("### 证据链接")
        links = structured.get("evidence_links", [])
        if isinstance(links, list) and links:
            for item in links[:20]:
                if isinstance(item, str):
                    lines.append(f"- {item}")
        else:
            lines.append("- （未提供）")
        lines.append("")

    # 不回显完整原始 YAML，避免与结构化展示重复、拉长日报内容。
    if not structured:
        lines.append("> 智能体输出未能结构化解析，已省略原文展示以保持日报简洁。")
        lines.append("")
    return "\n".join(lines)


async def _run_agent(agent_name: str, prompt: str) -> dict[str, Any]:
    base_prompt = load_prompt(agent_name)
    if not base_prompt:
        raise RuntimeError(f"Prompt not found for agent: {agent_name}")
    final_prompt = f"{base_prompt}\n\n---\n\n{prompt}"
    return await run_single_agent(final_prompt, agent_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ops daily diagnosis from facts JSON")
    parser.add_argument("--facts", required=True, help="Facts JSON path")
    parser.add_argument("--output", required=True, help="Output markdown path")
    parser.add_argument("--structured-output", default="", help="Optional parsed YAML JSON output path")
    parser.add_argument("--agent", default="ops_daily", help="Agent name")
    args = parser.parse_args()

    facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    prompt = _build_ops_prompt(facts)
    result = asyncio.run(_run_agent(args.agent, prompt))
    response = str(result.get("response", "")).strip()
    structured = _parse_structured_output(response)
    evidence_ok = _has_evidence_links(structured)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown = _render_markdown(response, structured)
    if not evidence_ok:
        markdown += "\n> 证据不足：智能体未给出有效 evidence_links，建议以 facts 层为准。\n"
    output.write_text(markdown, encoding="utf-8")
    print(f"agent diagnosis generated: {output}")

    if args.structured_output:
        structured_path = Path(args.structured_output)
        structured_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ok": bool(result.get("ok", True)),
            "agent": args.agent,
            "structured": structured,
            "evidence_ok": evidence_ok,
            "raw_response": response,
            "cost_usd": result.get("cost_usd", 0.0),
            "num_turns": result.get("num_turns", 0),
        }
        structured_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"agent structured output generated: {structured_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
