"""Claude Agent SDK 选项构建

处理 SDK 选项的创建和缓存管理。
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from issuelab.agents.config import AgentConfig
from issuelab.agents.discovery import AGENTS_DIR, discover_agents
from issuelab.config import Config
from issuelab.logging_config import get_logger

logger = get_logger(__name__)

# 全局缓存：存储 Agent 选项
_cached_agent_options: dict[tuple, ClaudeAgentOptions] = {}


def clear_agent_options_cache() -> None:
    """清除 Agent 选项缓存

    在测试或配置更改后调用此函数以确保使用最新的配置。
    """
    global _cached_agent_options
    _cached_agent_options = {}
    logger.info("Agent 选项缓存已清除")


def _read_mcp_servers_from_file(path: Path) -> dict[str, Any]:
    """读取 .mcp.json 并返回 mcpServers 字典

    支持两种格式：
    1) {"mcpServers": { ... }}
    2) { ... }  # 直接就是 servers 映射
    """
    if not path.exists():
        return {}

    try:
        raw_text = _read_text_with_timeout(path)
        raw = json.loads(raw_text)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 MCP 配置失败: %s (%s)", path, exc)
        return {}
    except TimeoutError as exc:
        logger.warning("读取 MCP 配置超时，已跳过: %s (%s)", path, exc)
        return {}

    if not isinstance(raw, dict):
        logger.warning("MCP 配置格式错误（非 dict）: %s", path)
        return {}

    servers = raw.get("mcpServers", raw)
    if not isinstance(servers, dict):
        logger.warning("MCP 配置格式错误（mcpServers 非 dict）: %s", path)
        return {}

    return servers


def _read_text_with_timeout(path: Path) -> str:
    """读取文件内容（带超时）"""
    timeout_ms = int(os.environ.get("MCP_CONFIG_LOAD_TIMEOUT_MS", "3000"))
    timeout_sec = max(timeout_ms, 0) / 1000.0

    def _read() -> str:
        return path.read_text(encoding="utf-8")

    if timeout_sec <= 0:
        return _read()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_read)
        try:
            return future.result(timeout=timeout_sec)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"read timeout after {timeout_ms}ms") from exc


def load_mcp_servers_for_agent(agent_name: str | None, root_dir: Path | None = None) -> dict[str, Any]:
    """加载 MCP 服务器配置（全局 + per-agent 覆盖）"""
    root = root_dir or AGENTS_DIR.parent
    servers: dict[str, Any] = {}

    # 全局配置：项目根目录 .mcp.json
    servers.update(_read_mcp_servers_from_file(root / ".mcp.json"))

    # Agent 级别配置：agents/<name>/.mcp.json
    if agent_name:
        servers.update(_read_mcp_servers_from_file(root / "agents" / agent_name / ".mcp.json"))

    return servers


def format_mcp_servers_for_prompt(agent_name: str | None, root_dir: Path | None = None) -> str:
    """为 prompt 格式化 MCP 服务器列表"""
    servers = load_mcp_servers_for_agent(agent_name, root_dir=root_dir)
    if not servers:
        return "（未配置 MCP 工具）"
    lines = []
    for name, cfg in servers.items():
        cfg_type = ""
        if isinstance(cfg, dict):
            cfg_type = cfg.get("type", "")
        type_text = f" [{cfg_type}]" if cfg_type else ""
        lines.append(f"- {name}{type_text}")
    return "\n".join(lines)


def _run_async_in_thread(coro, timeout_ms: int) -> Any:
    """在独立线程中运行 async 任务，避免与当前事件循环冲突"""
    timeout_sec = max(timeout_ms, 0) / 1000.0

    def _runner():
        import anyio
        async def _async_runner():
            return await coro

        return anyio.run(_async_runner)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        try:
            return future.result(timeout=timeout_sec if timeout_sec > 0 else None)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"async task timeout after {timeout_ms}ms") from exc


async def _list_tools_stdio(server_name: str, cfg: dict[str, Any]) -> list[str]:
    """通过 MCP stdio 连接列出工具"""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=cfg.get("command", ""),
        args=cfg.get("args", []) or [],
        env=cfg.get("env"),
        cwd=cfg.get("cwd"),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        result = await session.list_tools()
        tools = result.tools or []
        return [t.name for t in tools if getattr(t, "name", None)]


def _list_tools_for_mcp_server(server_name: str, cfg: dict[str, Any], timeout_ms: int) -> list[str]:
    """列出单个 MCP server 的工具（目前仅支持 stdio）"""
    if not isinstance(cfg, dict):
        return []

    if "command" not in cfg:
        logger.debug("Skip MCP tool listing for '%s': non-stdio server", server_name)
        return []

    try:
        return _run_async_in_thread(_list_tools_stdio(server_name, cfg), timeout_ms=timeout_ms)
    except TimeoutError as exc:
        logger.warning("List tools timeout for MCP server '%s': %s", server_name, exc)
        return []
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("List tools failed for MCP server '%s': %s", server_name, exc)
        return []


def _mcp_cache_key(servers: dict[str, Any]) -> str:
    """生成 MCP 配置的稳定缓存键"""
    if not servers:
        return ""
    try:
        return json.dumps(servers, sort_keys=True, ensure_ascii=True)
    except TypeError:
        return str(servers)


def _create_agent_options_impl(
    max_turns: int | None,
    max_budget_usd: float | None,
    *,
    agent_name: str | None,
    mcp_servers: dict[str, Any],
) -> ClaudeAgentOptions:
    """创建 Agent 选项的实际实现（无缓存）"""
    env = Config.get_anthropic_env()
    env["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "true"

    # 收集 SDK 内部日志的回调
    sdk_logs: list[str] = []

    def sdk_stderr_handler(message: str) -> None:
        """捕获 SDK 内部日志（包含详细的模型交互信息）"""
        log_entry = f"[SDK] {message}"
        sdk_logs.append(log_entry)
        # 输出到终端
        print(message, end="", flush=True)
        # 记录到日志
        logger.debug(f"[SDK] {message}")

    agents = discover_agents()

    base_tools = ["Read", "Write", "Bash"]
    all_tools = base_tools
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

    allowed_tools = base_tools[:]
    if mcp_servers:
        allowed_tools.extend([f"mcp__{name}__*" for name in mcp_servers])
    if os.environ.get("MCP_LOG_DETAIL") == "1":
        logger.debug("Allowed tools for agent '%s': %s", agent_name or "default", allowed_tools)

    return ClaudeAgentOptions(
        agents=agent_definitions,
        max_turns=max_turns if max_turns is not None else AgentConfig().max_turns,
        max_budget_usd=max_budget_usd if max_budget_usd is not None else AgentConfig().max_budget_usd,
        setting_sources=["user", "project"],
        env=env,
        permission_mode="bypassPermissions",
        allowed_tools=allowed_tools,
        mcp_servers=mcp_servers,
        stderr=sdk_stderr_handler,  # 捕获 SDK 内部详细日志
    )


def create_agent_options(
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    *,
    agent_name: str | None = None,
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
    mcp_servers = load_mcp_servers_for_agent(agent_name)
    if mcp_servers:
        server_names = ", ".join(sorted(mcp_servers.keys()))
        logger.info("MCP servers loaded for agent '%s': %s", agent_name or "default", server_names)
    else:
        logger.info("No MCP servers configured for agent '%s'", agent_name or "default")

    if os.environ.get("MCP_LOG_DETAIL") == "1":
        logger.debug("MCP servers detail for agent '%s': %s", agent_name or "default", mcp_servers)

    if os.environ.get("MCP_LOG_TOOLS") == "1" and mcp_servers:
        timeout_ms = int(os.environ.get("MCP_LIST_TOOLS_TIMEOUT_MS", "3000"))
        for name, cfg in mcp_servers.items():
            tools = _list_tools_for_mcp_server(name, cfg, timeout_ms=timeout_ms)
            if tools:
                logger.info("MCP tools for '%s': %s", name, ", ".join(sorted(tools)))
            else:
                logger.info("MCP tools for '%s': (none or unavailable)", name)
    cache_key = (effective_max_turns, effective_max_budget, agent_name or "", _mcp_cache_key(mcp_servers))

    # 检查缓存
    if cache_key in _cached_agent_options:
        logger.debug(f"使用缓存的 Agent 选项 (key={cache_key})")
        return _cached_agent_options[cache_key]

    # 创建新配置
    options = _create_agent_options_impl(
        max_turns,
        max_budget_usd,
        agent_name=agent_name,
        mcp_servers=mcp_servers,
    )

    # 存入缓存
    _cached_agent_options[cache_key] = options
    logger.debug(f"创建新的 Agent 选项并缓存 (key={cache_key})")

    return options
