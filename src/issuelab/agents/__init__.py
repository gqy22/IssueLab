"""代理模块：统一的Agent管理接口

本模块提供动态发现和管理评审代理的功能，
所有Agent通过扫描prompts/目录自动注册。
"""

# 直接从子模块导入核心功能
from issuelab.agents.discovery import (
    discover_agents,
    load_prompt,
    parse_agent_metadata,
)
from issuelab.agents.registry import AGENT_NAMES, BUILTIN_AGENTS, normalize_agent_name


def get_available_agents() -> list[str]:
    """获取所有可用代理名称

    Returns:
        代理名称列表
    """
    agents = discover_agents()
    return list(agents.keys())


__all__ = [
    "discover_agents",
    "load_prompt",
    "parse_agent_metadata",
    "normalize_agent_name",
    "get_available_agents",
    "AGENT_NAMES",
    "BUILTIN_AGENTS",
]
