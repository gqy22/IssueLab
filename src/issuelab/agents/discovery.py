"""Agent 发现和管理

动态发现并管理系统中的所有 Agent 配置。
"""

from pathlib import Path
from typing import Any

# 统一 registry 读取
from issuelab.agents.registry import load_registry

AGENTS_DIR = Path(__file__).parent.parent.parent.parent / "agents"

# 进程级缓存
_CACHED_AGENTS: dict[str, dict[str, Any]] | None = None
_CACHED_SIGNATURE: tuple[tuple[str, float], ...] | None = None


def _get_discovery_signature() -> tuple:
    """生成当前 agents 配置签名（基于文件 mtime）"""
    signature: list[tuple[str, float]] = []

    if AGENTS_DIR.exists():
        for user_dir in sorted(AGENTS_DIR.iterdir()):
            if not user_dir.is_dir():
                continue
            for name in ("agent.yml", "prompt.md"):
                path = user_dir / name
                if not path.exists():
                    continue
                try:
                    signature.append((f"agents/{user_dir.name}/{name}", path.stat().st_mtime))
                except OSError:
                    continue

    return tuple(signature)


def discover_agents() -> dict[str, dict[str, Any]]:
    """动态发现所有可用的 Agent

    通过读取 agents/<name>/agent.yml + prompt.md

    Returns:
        {
            "agent_name": {
                "description": "Agent 描述",
                "prompt": "完整 prompt 内容",
                "trigger_conditions": ["触发条件1", "触发条件2"],
            }
        }
    """
    global _CACHED_AGENTS, _CACHED_SIGNATURE

    signature = _get_discovery_signature()
    if _CACHED_AGENTS is not None and signature == _CACHED_SIGNATURE:
        return _CACHED_AGENTS

    agents: dict[str, dict[str, Any]] = {}
    if AGENTS_DIR.exists():
        registry = load_registry(AGENTS_DIR, include_disabled=False)

        for agent_name, agent_config in registry.items():
            agent_dir = AGENTS_DIR / agent_name
            prompt_file = agent_dir / "prompt.md"
            if not prompt_file.exists():
                continue

            prompt_content = prompt_file.read_text()
            clean_content = prompt_content.strip()

            description = str(agent_config.get("description", ""))
            trigger_conditions = agent_config.get("triggers", [])
            if not isinstance(trigger_conditions, list):
                trigger_conditions = []

            agents[agent_name] = {
                "description": description,
                "prompt": clean_content,
                "trigger_conditions": trigger_conditions,
            }

    _CACHED_AGENTS = agents
    _CACHED_SIGNATURE = signature
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
