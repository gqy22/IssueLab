"""SDK 执行器：使用 Claude Agent SDK 构建评审代理"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    query,
)

from issuelab.config import Config
from issuelab.logging_config import get_logger
from issuelab.retry import retry_async

logger = get_logger(__name__)

# 提示词目录
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"


@dataclass
class AgentConfig:
    """Agent 执行配置（超时控制）

    官方推荐使用 max_turns 防止无限循环：
    https://platform.claude.com/docs/en/agent-sdk/hosting

    Attributes:
        max_turns: 最大对话轮数（防止无限循环）
        max_budget_usd: 最大花费限制（成本保护）
        timeout_seconds: 总超时时间（秒）
    """

    max_turns: int = 3
    max_budget_usd: float = 0.50
    timeout_seconds: int = 180


# 场景配置
SCENE_CONFIGS: dict[str, AgentConfig] = {
    "quick": AgentConfig(
        max_turns=2,
        max_budget_usd=0.20,
        timeout_seconds=60,
    ),
    "review": AgentConfig(
        max_turns=3,
        max_budget_usd=0.50,
        timeout_seconds=180,
    ),
    "deep": AgentConfig(
        max_turns=5,
        max_budget_usd=1.00,
        timeout_seconds=300,
    ),
}


def get_agent_config_for_scene(scene: str = "review") -> AgentConfig:
    """根据场景获取配置

    Args:
        scene: 场景名称 ("quick", "review", "deep")
        default: "review"

    Returns:
        AgentConfig: 对应的场景配置
    """
    return SCENE_CONFIGS.get(scene, SCENE_CONFIGS["review"])


# ========== 缓存机制 ==========

# 全局缓存：存储 Agent 选项
_cached_agent_options: dict[tuple, ClaudeAgentOptions] = {}


def clear_agent_options_cache() -> None:
    """清除 Agent 选项缓存

    在测试或配置更改后调用此函数以确保使用最新的配置。
    """
    global _cached_agent_options
    _cached_agent_options = {}
    logger.info("Agent 选项缓存已清除")


def _create_agent_options_impl(
    max_turns: int | None,
    max_budget_usd: float | None,
) -> ClaudeAgentOptions:
    """创建 Agent 选项的实际实现（无缓存）"""
    env = Config.get_anthropic_env()
    env["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "true"

    arxiv_storage_path = Config.get_arxiv_storage_path()

    mcp_servers = []
    if Config.is_arxiv_mcp_enabled():
        mcp_servers.append(
            {
                "name": "arxiv-mcp-server",
                "command": "arxiv-mcp-server",
                "args": ["--storage-path", arxiv_storage_path],
                "env": env.copy(),
            }
        )

    if Config.is_github_mcp_enabled():
        mcp_servers.append(
            {
                "name": "github-mcp-server",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": env.copy(),
            }
        )

    agents = discover_agents()

    base_tools = ["Read", "Write", "Bash"]

    arxiv_tools = []
    if os.environ.get("ENABLE_ARXIV_MCP", "true").lower() == "true":
        arxiv_tools = ["search_papers", "download_paper", "read_paper", "list_papers"]

    github_tools = []
    if os.environ.get("ENABLE_GITHUB_MCP", "true").lower() == "true":
        github_tools = [
            "search_repositories",
            "get_file_contents",
            "list_commits",
            "search_code",
            "get_issue",
        ]

    all_tools = base_tools + arxiv_tools + github_tools
    model = Config.get_anthropic_model()

    agent_definitions = {}
    for name, config in agents.items():
        if name == "observer":
            continue
        agent_definitions[name] = AgentDefinition(
            description=config["description"],
            prompt=config["prompt"],
            tools=all_tools,
            model=model,
        )

    return ClaudeAgentOptions(
        agents=agent_definitions,
        max_turns=max_turns if max_turns is not None else AgentConfig().max_turns,
        max_budget_usd=max_budget_usd if max_budget_usd is not None else AgentConfig().max_budget_usd,
        setting_sources=["user", "project"],
        env=env,
        mcp_servers=mcp_servers,
    )


def parse_agent_metadata(content: str) -> dict | None:
    """从 prompt 文件中解析 YAML 元数据

    格式：
    ---
    agent: moderator
    description: 分诊与控场代理
    trigger_conditions:
      - 新论文 Issue
      - 需要分配评审流程
    ---
    """
    # 匹配 YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return None

    yaml_str = match.group(1)
    metadata = {}
    current_list_key = None
    current_list = []

    # 解析 YAML
    for line in yaml_str.split("\n"):
        line = line.rstrip()

        # 检测列表项
        if line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            current_list.append(item)
            # 找到最后一个列表键
            for key in ["trigger_conditions"]:
                if key in metadata:
                    current_list_key = key
            continue

        # 检测普通键值对
        if ":" in line and not line.strip().startswith("-"):
            # 先保存之前的列表
            if current_list and current_list_key:
                metadata[current_list_key] = current_list
                current_list = []
                current_list_key = None

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value:
                metadata[key] = value
            else:
                metadata[key] = None

    # 保存最后的列表
    if current_list and current_list_key:
        metadata[current_list_key] = current_list

    return metadata if metadata else None


def discover_agents() -> dict:
    """动态发现所有可用的 Agent

    通过读取 prompts 文件夹下的 .md 文件，解析 YAML 元数据

    Returns:
        {
            "agent_name": {
                "description": "Agent 描述",
                "prompt": "完整 prompt 内容",
                "trigger_conditions": ["触发条件1", "触发条件2"],
            }
        }
    """
    agents = {}

    if not PROMPTS_DIR.exists():
        return agents

    # 扫描 prompts 目录下的 .md 文件
    for prompt_file in PROMPTS_DIR.glob("*.md"):
        content = prompt_file.read_text()
        metadata = parse_agent_metadata(content)

        if metadata and "agent" in metadata:
            agent_name = metadata["agent"]
            # 移除 frontmatter，获取纯 prompt 内容
            clean_content = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()

            agents[agent_name] = {
                "description": metadata.get("description", ""),
                "prompt": clean_content,
                "trigger_conditions": metadata.get("trigger_conditions", []),
            }

    # 扫描 agents 目录下的 prompt.md 文件
    if AGENTS_DIR.exists():
        for agent_dir in AGENTS_DIR.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue

            prompt_file = agent_dir / "prompt.md"
            if prompt_file.exists():
                content = prompt_file.read_text()
                metadata = parse_agent_metadata(content)

                if metadata and "agent" in metadata:
                    # 优先使用 metadata 中的 agent 名，通常应该与目录名（用户 handle）一致
                    agent_name = metadata["agent"]

                    # 如果 metadata 中的名叫 gqy22-reviewer，但目录名叫 gqy22
                    # 为了兼容 @mention (解析出来是 gqy22)，我们可能需要同时也注册一个 gqy22 的别名
                    # 但在这里我们暂时信任 metadata 中的名字，或者也可以强制使用目录名
                    # 这里尝试一个回退策略：如果 URL/CLI 使用的是目录名，但也注册此 agent

                    # 移除 frontmatter
                    clean_content = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()

                    agent_data = {
                        "description": metadata.get("description", ""),
                        "prompt": clean_content,
                        "trigger_conditions": metadata.get("trigger_conditions", []),
                    }

                    agents[agent_name] = agent_data

                    # 如果目录名与 agent_name 不同，也注册别名（指向同一个配置）
                    # 这样 @gqy22 (目录名) 也能找到 agent: gqy22-reviewer
                    if agent_dir.name != agent_name:
                        agents[agent_dir.name] = agent_data

    return agents


def get_agent_matrix_markdown() -> str:
    """生成 Agent 矩阵的 Markdown 表格（用于 Observer Prompt）"""
    agents = discover_agents()

    lines = [
        "| Agent | 描述 | 何时触发 |",
        "|-------|------|---------|",
    ]

    for name, config in agents.items():
        if name == "observer":
            continue  # Observer 不需要被自己触发
        trigger_conditions = config.get("trigger_conditions", [])
        trigger = ", ".join(trigger_conditions) if trigger_conditions else "自动判断"
        desc = config.get("description", "")
        lines.append(f"| **{name}** | {desc} | {trigger} |")

    return "\n".join(lines)


def load_prompt(agent_name: str) -> str:
    """加载代理提示词（从动态发现的 agents 中）"""
    agents = discover_agents()
    if agent_name in agents:
        return agents[agent_name]["prompt"]
    return ""


def create_agent_options(
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
) -> ClaudeAgentOptions:
    """创建包含所有评审代理的配置（动态发现）

    官方推荐的超时控制参数：
    - max_turns: 限制对话轮数，防止无限循环
    - max_budget_usd: 限制花费，防止意外支出

    Args:
        max_turns: 最大对话轮数（默认使用 AgentConfig 默认值）
        max_budget_usd: 最大花费限制（默认使用 AgentConfig 默认值）

    Returns:
        ClaudeAgentOptions: 配置好的 SDK 选项

    Note:
        此函数使用缓存来避免重复创建相同的配置。
        如果需要强制刷新配置，请先调用 clear_agent_options_cache()。
    """
    # 使用默认值
    effective_max_turns = max_turns if max_turns is not None else AgentConfig().max_turns
    effective_max_budget = max_budget_usd if max_budget_usd is not None else AgentConfig().max_budget_usd

    # 缓存键：使用参数元组
    cache_key = (effective_max_turns, effective_max_budget)

    # 检查缓存
    if cache_key in _cached_agent_options:
        logger.debug(f"使用缓存的 Agent 选项 (key={cache_key})")
        return _cached_agent_options[cache_key]

    # 创建新配置
    options = _create_agent_options_impl(max_turns, max_budget_usd)

    # 存入缓存
    _cached_agent_options[cache_key] = options
    logger.debug(f"创建新的 Agent 选项并缓存 (key={cache_key})")

    return options


async def run_single_agent(prompt: str, agent_name: str) -> str:
    """运行单个代理（带重试机制）

    Args:
        prompt: 用户提示词
        agent_name: 代理名称

    Returns:
        代理响应文本
    """
    logger.info(f"开始运行 agent: {agent_name}")

    async def _query_agent():
        options = create_agent_options()
        response_text = []

        async for message in query(
            prompt=prompt,
            options=options,
        ):
            from claude_agent_sdk import AssistantMessage, TextBlock

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)

        result = "\n".join(response_text)
        logger.info(f"Agent {agent_name} 响应完成，长度: {len(result)} 字符")
        return result

    try:
        return await retry_async(_query_agent, max_retries=3, initial_delay=2.0, backoff_factor=2.0)
    except Exception as e:
        logger.error(f"Agent {agent_name} 运行失败: {e}", exc_info=True)
        return f"[错误] Agent {agent_name} 执行失败: {e}"


async def run_agents_parallel(issue_number: int, agents: list[str], context: str = "", comment_count: int = 0) -> dict:
    """串行运行多个代理（函数名保持向后兼容）

    注意：虽然函数名为 parallel，但实际改为串行执行以避免 Claude Agent SDK 的资源竞争问题。

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
        context: 上下文信息
        comment_count: 评论数量（用于增强上下文）

    Returns:
        {agent_name: response_text}
    """
    # 构建增强的上下文
    full_context = context
    if comment_count > 0:
        full_context += f"\n\n**重要提示**: 本 Issue 已有 {comment_count} 条历史评论。Summarizer 代理应读取并分析这些评论，提取共识、分歧和行动项。"

    base_prompt = f"""请对 GitHub Issue #{issue_number} 执行以下任务：

{full_context}

请以 [Agent: {{agent_name}}] 为前缀发布你的回复。"""

    results = {}

    # 串行执行以避免 Claude Agent SDK 资源竞争
    for agent in agents:
        prompt = base_prompt.format(agent_name=agent)
        logger.info(f"串行执行 agent: {agent} ({agents.index(agent) + 1}/{len(agents)})")
        response = await run_single_agent(prompt, agent)
        results[agent] = response

    return results


async def run_observer(issue_number: int, issue_title: str = "", issue_body: str = "", comments: str = "") -> dict:
    """运行 Observer Agent

    Observer Agent 会分析 Issue 并决定是否需要触发其他 Agent。

    Args:
        issue_number: Issue 编号
        issue_title: Issue 标题
        issue_body: Issue 内容
        comments: 历史评论

    Returns:
        {
            "should_trigger": bool,
            "agent": str,  # 要触发的 Agent 名称
            "comment": str,  # 触发评论内容
            "reason": str,  # 触发理由
            "analysis": str,  # Issue 分析
        }
    """
    agents = discover_agents()
    observer_config = agents.get("observer", {})

    if not observer_config:
        return {
            "should_trigger": False,
            "error": "Observer agent not found",
        }

    # 动态生成 Agent 矩阵
    agent_matrix = get_agent_matrix_markdown()

    prompt = observer_config["prompt"].format(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body or "无内容",
        comments=comments or "无评论",
        agent_matrix=agent_matrix,
    )

    response = await run_single_agent(prompt, "observer")

    # 解析响应
    return parse_observer_response(response, issue_number)


async def run_observer_batch(issue_data_list: list[dict]) -> list[dict]:
    """并行运行 Observer Agent 分析多个 Issues

    Args:
        issue_data_list: Issue 数据列表，每个元素包含:
            {
                "issue_number": int,
                "issue_title": str,
                "issue_body": str,
                "comments": str,
            }

    Returns:
        分析结果列表，每个元素包含 issue_number 和决策结果
    """
    logger.info(f"开始并行分析 {len(issue_data_list)} 个 Issues")

    results = []
    async with anyio.create_task_group() as tg:

        async def analyze_one(issue_data: dict):
            issue_number = issue_data["issue_number"]
            try:
                result = await run_observer(
                    issue_number=issue_number,
                    issue_title=issue_data.get("issue_title", ""),
                    issue_body=issue_data.get("issue_body", ""),
                    comments=issue_data.get("comments", ""),
                )
                result["issue_number"] = issue_number
                results.append(result)
                logger.info(f"Issue #{issue_number} 分析完成: should_trigger={result.get('should_trigger')}")
            except Exception as e:
                logger.error(f"Issue #{issue_number} 分析失败: {e}", exc_info=True)
                results.append(
                    {
                        "issue_number": issue_number,
                        "should_trigger": False,
                        "error": str(e),
                    }
                )

        for issue_data in issue_data_list:
            tg.start_soon(analyze_one, issue_data)

    logger.info(f"并行分析完成，总计 {len(results)} 个结果")
    return results


def parse_observer_response(response: str, issue_number: int) -> dict:
    """解析 Observer Agent 的响应

    支持 YAML 格式（使用 PyYAML）和兼容的行扫描格式。

    Args:
        response: Agent 响应文本
        issue_number: Issue 编号

    Returns:
        解析后的决策结果 {
            "should_trigger": bool,
            "agent": str,
            "comment": str,
            "reason": str,
            "analysis": str,
        }
    """
    import yaml

    result = {
        "should_trigger": False,
        "agent": "",
        "comment": "",
        "reason": "",
        "analysis": "",
    }

    # 方法1: 尝试 YAML 解析
    yaml_data = _try_parse_yaml(response)
    if yaml_data is not None:
        result["should_trigger"] = yaml_data.get("should_trigger", False)
        result["agent"] = yaml_data.get("agent", "") or yaml_data.get("trigger_agent", "")
        result["comment"] = yaml_data.get("comment", "") or yaml_data.get("trigger_comment", "")
        result["reason"] = yaml_data.get("reason", "") or yaml_data.get("skip_reason", "")
        result["analysis"] = yaml_data.get("analysis", "")

        # 如果是 skip 模式，提前返回
        if not result["should_trigger"] and result["reason"]:
            return result

        # 如果没有解析到触发评论，使用默认格式
        if result["should_trigger"] and result["agent"] and not result["comment"]:
            result["comment"] = _get_default_trigger_comment(result["agent"])

        return result

    # 方法2: 回退到行扫描（兼容旧格式）
    return _parse_observer_response_lines(response, result, issue_number)


def _try_parse_yaml(response: str) -> dict | None:
    """尝试解析 YAML 格式的响应

    Args:
        response: Agent 响应文本

    Returns:
        解析后的字典，失败返回 None
    """
    import yaml

    # 清理响应文本
    text = response.strip()

    # 检查是否包含 YAML 代码块标记
    if "```yaml" in text:
        # 提取 ```yaml 和 ``` 之间的内容
        start = text.find("```yaml")
        if start == -1:
            start = text.find("```")
        end = text.rfind("```")
        if start != -1 and end != -1 and end > start:
            # 找到代码块内容（跳过 ```yaml 行和 ``` 行）
            lines = text[start:end].split("\n")
            if len(lines) >= 2:
                yaml_content = "\n".join(lines[1:])
                try:
                    return yaml.safe_load(yaml_content)
                except yaml.YAMLError:
                    pass
    elif text.startswith("---"):
        # 可能直接是 YAML 文档
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            pass

    # 检查是否是简单的键值对格式（每行一个）
    lines = text.split("\n")
    yaml_like = True
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            yaml_like = False
            break

    if yaml_like:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            pass

    return None


def _parse_observer_response_lines(response: str, result: dict, issue_number: int) -> dict:
    """回退解析：简单的行扫描（兼容旧格式）"""
    lines = response.split("\n")

    # 查找 action/should_trigger
    for line in lines:
        line_lower = line.lower().strip()
        if "action: trigger" in line_lower or "should_trigger: true" in line_lower:
            result["should_trigger"] = True
        elif "action: skip" in line_lower or "should_trigger: false" in line_lower:
            result["should_trigger"] = False
            return result

    # 查找 agent
    for line in lines:
        if line.startswith("agent:") or line.startswith("trigger_agent:"):
            result["agent"] = line.split(":", 1)[1].strip().lower()
            break

    # 查找 comment（处理简单的单行格式）
    for line in lines:
        if line.lower().startswith("comment:") or line.lower().startswith("trigger_comment:"):
            result["comment"] = line.split(":", 1)[1].strip()
            break

    # 查找 reason
    for line in lines:
        if line.lower().startswith("reason:") or line.lower().startswith("skip_reason:"):
            result["reason"] = line.split(":", 1)[1].strip()
            break

    # 查找 analysis
    for line in lines:
        if line.lower().startswith("analysis:"):
            result["analysis"] = line.split(":", 1)[1].strip()
            break

    # 如果没有解析到触发评论，使用默认格式
    if result["should_trigger"] and result["agent"] and not result["comment"]:
        result["comment"] = _get_default_trigger_comment(result["agent"])

    return result


def _get_default_trigger_comment(agent: str) -> str:
    """获取默认的触发评论

    Args:
        agent: Agent 名称

    Returns:
        默认的触发评论
    """
    agent_map = {
        "moderator": "@Moderator 请分诊",
        "reviewer_a": "@ReviewerA 评审",
        "reviewer_b": "@ReviewerB 找问题",
        "summarizer": "@Summarizer 汇总",
        "observer": "@Observer",
    }
    return agent_map.get(agent, f"@{agent}")
