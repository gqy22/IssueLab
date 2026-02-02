"""代理模块：统一的Agent管理接口

本模块提供动态发现和管理评审代理的功能，
所有Agent通过扫描prompts/目录自动注册。
"""

# 直接从 sdk_executor 导入核心功能
# 从 parser 导入别名配置（单一来源）
from issuelab.parser import AGENT_ALIASES
from issuelab.sdk_executor import (
    discover_agents,
    load_prompt,
    parse_agent_metadata,
)


def normalize_agent_name(name: str) -> str:
    """标准化代理名称（支持别名）

    Args:
        name: 原始名称（可能包含别名）

    Returns:
        标准化的代理名称
    """
    return AGENT_ALIASES.get(name.lower(), name)


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
    "AGENT_ALIASES",
]
