"""Agent 执行器核心

处理 Agent 的执行、消息流和日志记录。
"""

import os
import re
import sys
from typing import Any, cast

import anyio
import yaml
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from issuelab.agents.config import AgentConfig
from issuelab.agents.options import create_agent_options, format_mcp_servers_for_prompt
from issuelab.logging_config import get_logger
from issuelab.retry import retry_async

logger = get_logger(__name__)

_OUTPUT_SCHEMA_BLOCK = (
    "\n\n## Output Format (required)\n"
    "请严格输出以下 YAML：\n\n"
    "```yaml\n"
    'summary: ""\n'
    "findings:\n"
    '  - ""\n'
    "recommendations:\n"
    '  - ""\n'
    'confidence: "low|medium|high"\n'
    "```\n"
)


def _append_output_schema(prompt: str) -> str:
    """为 prompt 注入统一输出格式（如果尚未注入）。"""
    if "## Output Format (required)" in prompt:
        return prompt
    return f"{prompt}{_OUTPUT_SCHEMA_BLOCK}"


async def run_single_agent(prompt: str, agent_name: str) -> dict:
    """运行单个代理（带完善的中间日志监听）

    Args:
        prompt: 用户提示词
        agent_name: 代理名称

    Returns:
        {
            "response": str,  # 代理响应文本
            "cost_usd": float,  # 成本（美元）
            "num_turns": int,  # 对话轮数
            "tool_calls": list[str],  # 工具调用列表
            "local_id": str,  # 会话 ID
        }
    """
    logger.info(f"[{agent_name}] 开始运行 Agent")
    logger.debug(f"[{agent_name}] Prompt 长度: {len(prompt)} 字符")

    # 执行信息收集
    execution_info: dict[str, Any] = {
        "response": "",
        "cost_usd": 0.0,
        "num_turns": 0,
        "tool_calls": [],
        "local_id": "",
        "text_blocks": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    async def _query_agent():
        options = create_agent_options(agent_name=agent_name)
        response_text = []
        turn_count = 0
        tool_calls = []
        first_result = True

        effective_prompt = _append_output_schema(prompt)
        async for message in query(prompt=effective_prompt, options=options):
            # AssistantMessage: AI 响应（文本或工具调用）
            if isinstance(message, AssistantMessage):
                turn_count += 1
                logger.debug(f"[{agent_name}] 收到消息 (第 {turn_count} 轮)")

                for block in message.content:
                    # 文本块 → 终端流式输出 + INFO 日志
                    if isinstance(block, TextBlock):
                        text = block.text
                        response_text.append(text)
                        execution_info["text_blocks"].append(text)

                        # 终端流式输出（写入 stderr，避免污染 stdout）
                        print(text, end="", flush=True, file=sys.stderr)
                        # 日志记录（INFO 级别）
                        logger.info(f"[{agent_name}] [Text] {text[:100]}...")

                    # 思考块 → 输出思考过程
                    elif isinstance(block, ThinkingBlock):
                        thinking = getattr(block, "thinking", "")
                        if thinking:
                            thinking_preview = thinking[:200] + "..." if len(thinking) > 200 else thinking
                            logger.debug(f"[{agent_name}] [Thinking] {thinking_preview}")

                    # 工具调用块 → 终端显示 + INFO 日志
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name
                        tool_use_id = getattr(block, "tool_use_id", "")
                        tool_input = getattr(block, "input", {})
                        tool_calls.append(tool_name)
                        execution_info["tool_calls"].append(tool_name)

                        # 终端输出（写入 stderr，避免污染 stdout）
                        print(f"\n[{tool_name}] id={tool_use_id}", end="", flush=True, file=sys.stderr)
                        if tool_name == "Skill" or tool_name.startswith("Skill"):
                            logger.info(f"[{agent_name}] [Skill] {tool_name}(id={tool_use_id})")
                        if tool_name == "Task":
                            logger.info(f"[{agent_name}] [Subagent] Task(id={tool_use_id})")
                        # 详细日志输出
                        if isinstance(tool_input, dict):
                            import json

                            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
                            logger.info(f"[{agent_name}] [Tool] {tool_name}(id={tool_use_id})")
                            logger.debug(f"[{agent_name}] [ToolInput] {input_str}")
                        else:
                            logger.info(f"[{agent_name}] [Tool] {tool_name}(id={tool_use_id})")

                    # 工具结果块 → 只日志，不终端输出
                    elif isinstance(block, ToolResultBlock):
                        tool_use_id = getattr(block, "tool_use_id", "")
                        is_error = getattr(block, "is_error", False)
                        result = getattr(block, "result", "")
                        # 限制结果长度，避免日志过多
                        if isinstance(result, str) and len(result) > 500:
                            logger.info(f"[{agent_name}] [ToolResult] id={tool_use_id} error={is_error} (truncated)")
                            logger.debug(f"[{agent_name}] [ToolResult] id={tool_use_id}:\n{result[:500]}...")
                        else:
                            logger.info(f"[{agent_name}] [ToolResult] id={tool_use_id} error={is_error}")
                            if result:
                                logger.debug(f"[{agent_name}] [ToolResult] id={tool_use_id}: {result}")

            # ResultMessage: 执行结果（成本、统计信息）
            elif isinstance(message, ResultMessage):
                # 打印统计信息
                print("\n")
                session_id = message.session_id or ""
                cost_usd = message.total_cost_usd or 0.0
                result_turns = message.num_turns or turn_count
                usage = message.usage or {}
                input_tokens = int(usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

                execution_info["session_id"] = session_id
                execution_info["cost_usd"] = cost_usd
                execution_info["num_turns"] = result_turns
                execution_info["input_tokens"] = input_tokens
                execution_info["output_tokens"] = output_tokens
                execution_info["total_tokens"] = total_tokens

                # 只在第一次收到 ResultMessage 时记录
                if first_result:
                    logger.info(f"[{agent_name}] [Result] session_id={session_id}")
                    first_result = False

                # 日志记录成本和统计
                stats_line = (
                    f"[{agent_name}] [Stats] 成本: ${cost_usd:.4f}, 轮数: {result_turns}, 工具调用: {len(tool_calls)}"
                )
                if input_tokens or output_tokens or total_tokens:
                    stats_line += f", 输入Token: {input_tokens}, 输出Token: {output_tokens}, 总Token: {total_tokens}"
                logger.info(stats_line)

        result = "\n".join(response_text)
        return result

    def _get_timeout_seconds() -> int | None:
        config = None
        try:
            from issuelab.agents.registry import get_agent_config

            config = get_agent_config(agent_name)
        except Exception:
            config = None

        if config and "timeout_seconds" in config:
            try:
                value = int(config["timeout_seconds"])
                return value if value > 0 else None
            except (TypeError, ValueError):
                return None
        return AgentConfig().timeout_seconds

    try:
        timeout_seconds = _get_timeout_seconds()
        if timeout_seconds:
            with anyio.fail_after(timeout_seconds):
                response = cast(
                    str,
                    await retry_async(_query_agent, max_retries=3, initial_delay=2.0, backoff_factor=2.0),
                )
        else:
            response = cast(
                str,
                await retry_async(_query_agent, max_retries=3, initial_delay=2.0, backoff_factor=2.0),
            )
        execution_info["response"] = response

        # 最终日志
        logger.info(
            f"[{agent_name}] 完成 - "
            f"响应长度: {len(response)} 字符, "
            f"成本: ${execution_info['cost_usd']:.4f}, "
            f"轮数: {execution_info['num_turns']}, "
            f"工具调用: {len(execution_info['tool_calls'])}, "
            f"输入Token: {execution_info['input_tokens']}, "
            f"输出Token: {execution_info['output_tokens']}, "
            f"总Token: {execution_info['total_tokens']}"
        )

        return execution_info
    except Exception as e:
        logger.error(f"[{agent_name}] 运行失败: {e}", exc_info=True)
        return {
            "response": f"[错误] Agent {agent_name} 执行失败: {e}",
            "cost_usd": 0.0,
            "num_turns": 0,
            "tool_calls": [],
            "session_id": "",
            "text_blocks": [],
        }


async def run_single_agent_text(prompt: str, agent_name: str | None = None) -> str:
    """轻量封装：只返回响应文本"""
    name = agent_name or "default"
    result = await run_single_agent(prompt, name)
    return result.get("response", "")


def _extract_urls(text: str) -> list[str]:
    """从文本中提取去重后的 URL 列表。"""
    if not text:
        return []
    found = re.findall(r"https?://[^\s)>\]\"']+", text)
    urls: list[str] = []
    for url in found:
        cleaned = url.rstrip(".,;:!?")
        if cleaned not in urls:
            urls.append(cleaned)
    return urls


def _extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_sources_from_yaml(text: str) -> list[str]:
    """从 YAML sources 字段提取 URL。"""
    yaml_text = _extract_yaml_block(text)
    if not yaml_text:
        return []
    try:
        parsed = yaml.safe_load(yaml_text) or {}
    except Exception:
        return []
    if not isinstance(parsed, dict):
        return []
    sources = parsed.get("sources", [])
    urls: list[str] = []
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, str):
                urls.extend(_extract_urls(item))
            elif isinstance(item, dict):
                url_value = str(item.get("url", "")).strip()
                if url_value:
                    urls.extend(_extract_urls(url_value))
    elif isinstance(sources, str):
        urls.extend(_extract_urls(sources))

    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _collect_source_urls(text: str) -> list[str]:
    """优先从 YAML sources 收集，否则回退为全文 URL。"""
    from_yaml = _extract_sources_from_yaml(text)
    if from_yaml:
        return from_yaml
    return _extract_urls(text)


def _is_gqy20_multistage_enabled(agent_name: str) -> bool:
    if agent_name != "gqy20":
        return False
    return os.environ.get("ISSUELAB_GQY20_MULTISTAGE", "1").lower() not in {"0", "false", "no", "off"}


async def _run_gqy20_multistage(agent_prompt: str, issue_number: int, task_context: str) -> dict[str, Any]:
    """gqy20 专用多阶段流程：Researcher -> Analyst -> Critic -> Verifier -> Judge。"""
    stages: dict[str, str] = {}
    total_cost = 0.0
    total_turns = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    tool_calls: list[str] = []

    async def _run_stage(stage_name: str, task: str) -> str:
        nonlocal total_cost, total_turns, total_input_tokens, total_output_tokens, total_tokens
        stage_prompt = f"""{agent_prompt}

---

## Multi-Stage Workflow
你正在执行 gqy20 的多阶段高质量流程。
当前阶段：{stage_name}

请严格遵守：
- 优先大量使用可用工具进行检索、核验、对照
- 不得在证据不足时给出确定性结论
- 如涉及事实陈述，尽可能给出可追溯 URL

## 当前任务
{task}
"""
        result = await run_single_agent(stage_prompt, "gqy20")
        total_cost += float(result.get("cost_usd", 0.0))
        total_turns += int(result.get("num_turns", 0))
        total_input_tokens += int(result.get("input_tokens", 0))
        total_output_tokens += int(result.get("output_tokens", 0))
        total_tokens += int(result.get("total_tokens", 0))
        stage_tools = result.get("tool_calls", [])
        if isinstance(stage_tools, list):
            tool_calls.extend(str(t) for t in stage_tools)
        text = str(result.get("response", "")).strip()
        stages[stage_name] = text
        return text

    researcher_task = f"""
请先只做“证据收集”，不要下最终结论。

Issue #{issue_number} 上下文：
{task_context}

输出要求（YAML）：
```yaml
summary: ""
evidence:
  - claim: ""
    source: ""
    url: ""
    confidence: "low|medium|high"
open_questions:
  - ""
confidence: "low|medium|high"
```
"""
    research_text = await _run_stage("Researcher", researcher_task)

    analyst_task = f"""
基于 Researcher 证据，产出 2-3 个候选结论版本（不要最终定稿）。

Researcher 输出：
{research_text}

输出要求（YAML）：
```yaml
summary: ""
candidates:
  - id: "A"
    summary: ""
    findings:
      - ""
    recommendations:
      - ""
    sources:
      - ""
  - id: "B"
    summary: ""
    findings:
      - ""
    recommendations:
      - ""
    sources:
      - ""
confidence: "low|medium|high"
```
"""
    analyst_text = await _run_stage("Analyst", analyst_task)

    critic_task = f"""
逐条批判 Analyst 候选结论，识别逻辑漏洞、证据缺口、过度推断和缺失引用。

Researcher 输出：
{research_text}

Analyst 输出：
{analyst_text}

输出要求（YAML）：
```yaml
summary: ""
criticisms:
  - candidate_id: "A"
    issues:
      - ""
    missing_evidence:
      - ""
confidence: "low|medium|high"
```
"""
    critic_text = await _run_stage("Critic", critic_task)

    verifier_task = f"""
强制核验候选结论的来源链接与证据一致性。
要求尽可能调用工具验证链接是否可访问、内容是否支持对应结论。

Researcher 输出：
{research_text}

Analyst 输出：
{analyst_text}

Critic 输出：
{critic_text}

输出要求（YAML）：
```yaml
summary: ""
verified_sources:
  - url: ""
    status: "verified|partially_verified|unverified"
    supports:
      - ""
verification_gaps:
  - ""
confidence: "low|medium|high"
```
"""
    verifier_text = await _run_stage("Verifier", verifier_task)

    judge_base_task = f"""
请综合 Researcher/Analyst/Critic/Verifier 结果，给出最终结论。

要求：
- 必须优先使用已核验来源
- 必须输出可追溯链接（sources）
- 对不确定项明确标注

Researcher 输出：
{research_text}

Analyst 输出：
{analyst_text}

Critic 输出：
{critic_text}

Verifier 输出：
{verifier_text}

最终输出必须是 YAML：
```yaml
summary: ""
findings:
  - ""
recommendations:
  - ""
sources:
  - ""
uncertainties:
  - ""
confidence: "low|medium|high"
```
"""

    judge_text = ""
    source_urls: list[str] = []
    retry_feedback = ""
    for attempt in range(3):
        judge_task = judge_base_task
        if retry_feedback:
            judge_task += f"\n\n补充要求（第 {attempt + 1} 次尝试）：\n{retry_feedback}\n"
        judge_text = await _run_stage("Judge", judge_task)
        source_urls = _collect_source_urls(judge_text)
        if source_urls:
            break
        retry_feedback = "上一版缺少可追溯来源链接。请补全 sources 字段，给出具体 URL，并确保关键结论可追溯。"

    if not source_urls:
        logger.warning("[gqy20] 多阶段结果缺少 sources，触发单阶段回退")
        fallback_prompt = f"""{agent_prompt}

---

## 当前任务
你需要分析 GitHub Issue #{issue_number}：

{task_context}

---

输出要求（严格）：
- 以 [Agent: gqy20] 开头
- 必须给出可追溯来源链接（sources）
- 证据不足的内容必须明确标注“不确定/缺证据”
"""
        fallback_result = await run_single_agent(fallback_prompt, "gqy20")
        fallback_text = str(fallback_result.get("response", ""))
        fallback_urls = _collect_source_urls(fallback_text)
        if fallback_urls:
            judge_text = fallback_text
            total_cost += float(fallback_result.get("cost_usd", 0.0))
            total_turns += int(fallback_result.get("num_turns", 0))
            total_input_tokens += int(fallback_result.get("input_tokens", 0))
            total_output_tokens += int(fallback_result.get("output_tokens", 0))
            total_tokens += int(fallback_result.get("total_tokens", 0))
            stage_tools = fallback_result.get("tool_calls", [])
            if isinstance(stage_tools, list):
                tool_calls.extend(str(t) for t in stage_tools)

    unique_tools: list[str] = []
    for tool in tool_calls:
        if tool not in unique_tools:
            unique_tools.append(tool)

    return {
        "response": judge_text,
        "cost_usd": total_cost,
        "num_turns": total_turns,
        "tool_calls": unique_tools,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "stages": stages,
    }


async def run_agents_parallel(
    issue_number: int,
    agents: list[str],
    context: str = "",
    comment_count: int = 0,
    available_agents: list[dict] | None = None,
    trigger_comment: str | None = None,
) -> dict:
    """并行运行多个代理

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
        context: 上下文信息（Issue 标题、内容、评论等）
        comment_count: 评论数量（用于增强上下文）
        available_agents: 系统中可用的智能体列表

    Returns:
        {
            agent_name: {
                "response": str,
                "cost_usd": float,
                "num_turns": int,
                "tool_calls": list[str],
                "session_id": str,
            }
        }
    """
    from issuelab.agents.discovery import discover_agents, load_prompt
    from issuelab.agents.observer import run_observer_for_papers, run_pubmed_observer_for_papers
    from issuelab.agents.paper_extractors import (
        extract_issue_body,
        format_arxiv_reanalysis,
        format_pubmed_reanalysis,
        parse_arxiv_papers_from_issue,
        parse_pubmed_papers_from_issue,
    )
    from issuelab.collaboration import build_collaboration_guidelines

    # 构建任务上下文（Issue 信息）
    task_context = context
    if trigger_comment:
        task_context = "## 最新触发评论（最高优先级）\n" f"{trigger_comment}\n\n" "---\n\n" f"{task_context}"
    if comment_count > 0:
        task_context += f"\n\n**重要提示**: 本 Issue 已有 {comment_count} 条历史评论。请仔细阅读并分析这些评论。"

    # 协作指南：统一在执行器注入，覆盖所有入口（CLI/personal-reply/observer_trigger 等）
    # 为避免重复注入：如果上游 context 已包含协作指南标题，则跳过
    if "## 协作指南" not in task_context:
        agents_dict = discover_agents()
        collaboration_guidelines = build_collaboration_guidelines(agents_dict, available_agents=available_agents)
        if collaboration_guidelines:
            task_context += f"\n\n{collaboration_guidelines}"

    results: dict[str, dict] = {}
    total_cost = 0.0

    async def run_agent_task(agent_name: str, results: dict[str, dict]) -> None:
        """并行任务：运行单个 agent"""
        logger.info(f"[Issue#{issue_number}] [并行] 开始执行 {agent_name}")

        # 特殊：pubmed_observer / arxiv_observer 需要从 Issue 正文解析文献列表
        if agent_name in {"pubmed_observer", "arxiv_observer"}:
            issue_body = extract_issue_body(task_context)
            if agent_name == "pubmed_observer":
                papers, query = parse_pubmed_papers_from_issue(issue_body)
                if not papers:
                    results[agent_name] = {
                        "response": "[Agent: pubmed_observer]\n未在 Issue 正文中识别到 PubMed 文献列表。",
                        "cost_usd": 0.0,
                        "num_turns": 0,
                        "tool_calls": [],
                    }
                    return

                recommended, raw_result = await run_pubmed_observer_for_papers(papers, query, return_result=True)
                response = format_pubmed_reanalysis(recommended, query, total=len(papers))
                raw_result["response"] = response
                results[agent_name] = raw_result
                return

            papers = parse_arxiv_papers_from_issue(issue_body)
            if not papers:
                results[agent_name] = {
                    "response": "[Agent: arxiv_observer]\n未在 Issue 正文中识别到 arXiv 论文信息。",
                    "cost_usd": 0.0,
                    "num_turns": 0,
                    "tool_calls": [],
                }
                return

            recommended, raw_result = await run_observer_for_papers(papers, return_result=True)
            response = format_arxiv_reanalysis(recommended, total=len(papers))
            raw_result["response"] = response
            results[agent_name] = raw_result
            return

        # 1. 加载 agent 的专属 prompt（定义角色和职责）
        agent_prompt = load_prompt(agent_name)
        if not agent_prompt:
            logger.warning(f"[{agent_name}] 未找到 prompt 文件，使用默认配置")
            agent_prompt = f"你是 {agent_name} 代理。"

        if "{mcp_servers}" in agent_prompt:
            mcp_text = format_mcp_servers_for_prompt(agent_name)
            agent_prompt = agent_prompt.replace("{mcp_servers}", mcp_text)

        # 2. 构建最终 prompt：角色定义 + 当前任务
        final_prompt = f"""{agent_prompt}

---

## 当前任务

你需要分析 GitHub Issue #{issue_number}：

{task_context}

---

**输出要求**：
- 请以 [Agent: {agent_name}] 为前缀发布你的回复
- 专注于 Issue 的讨论话题和内容
- 不要去分析项目代码或架构（除非 Issue 明确要求）
"""
        if os.environ.get("PROMPT_LOG") == "1":
            max_len = 2000
            preview = final_prompt[:max_len]
            suffix = "..." if len(final_prompt) > max_len else ""
            logger.debug(f"[{agent_name}] [Prompt] length={len(final_prompt)}\\n{preview}{suffix}")

        if _is_gqy20_multistage_enabled(agent_name):
            logger.info(f"[Issue#{issue_number}] {agent_name} 启用多阶段流程")
            result = await _run_gqy20_multistage(agent_prompt, issue_number, task_context)
        else:
            result = await run_single_agent(final_prompt, agent_name)
        results[agent_name] = result
        total_cost_local = result.get("cost_usd", 0.0)
        logger.info(
            f"[Issue#{issue_number}] {agent_name} 完成 - "
            f"成本: ${total_cost_local:.4f}, "
            f"轮数: {result.get('num_turns', 0)}, "
            f"工具: {len(result.get('tool_calls', []))}"
        )

    # 使用 anyio.create_task_group 实现真正的并行执行
    async with anyio.create_task_group() as tg:
        for agent in agents:
            tg.start_soon(run_agent_task, agent, results)

    # 汇总总成本
    total_cost = sum(r.get("cost_usd", 0.0) for r in results.values())
    logger.info(f"[Issue#{issue_number}] 所有 Agent 完成 - 总成本: ${total_cost:.4f}")
    return results
