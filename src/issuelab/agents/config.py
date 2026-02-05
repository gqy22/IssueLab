"""Agent 配置管理

提供场景化的 Agent 执行配置（超时、成本控制等）。
"""

from dataclasses import dataclass


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

    max_turns: int = 15
    max_budget_usd: float = 0.50
    timeout_seconds: int = 180


# 场景配置
SCENE_CONFIGS: dict[str, AgentConfig] = {
    "quick": AgentConfig(
        max_turns=10,
        max_budget_usd=0.20,
        timeout_seconds=60,
    ),
    "review": AgentConfig(
        max_turns=25,  # 增加到25轮，支持需要多次工具调用的agent（如summarizer）
        max_budget_usd=0.50,
        timeout_seconds=180,
    ),
    "deep": AgentConfig(
        max_turns=25,
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
