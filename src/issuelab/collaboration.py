"""协作配置模块 - 系统级 @mentions 指南

负责加载协作配置并构建协作指南，为所有 agents 统一提供协作能力。
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_collaboration_config() -> dict[str, Any]:
    """加载协作配置

    Returns:
        协作配置字典，如果加载失败返回默认配置（disabled）
    """
    config_paths = [
        Path(__file__).parent.parent.parent / "config" / "collaboration.yml",
        Path.cwd() / "config" / "collaboration.yml",
    ]

    config_file = None
    for path in config_paths:
        if path.exists():
            config_file = path
            break

    # 默认配置（禁用）
    default_config = {
        "enabled": False,
        "guidelines_template": "",
    }

    if not config_file:
        logger.debug("未找到 collaboration.yml，协作指南已禁用")
        return default_config

    try:
        import yaml

        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config or "collaboration" not in config:
            logger.warning("collaboration.yml 格式错误，协作指南已禁用")
            return default_config

        collaboration = config["collaboration"]
        logger.info(f"加载协作配置: enabled={collaboration.get('enabled', False)}")
        return collaboration

    except ImportError:
        logger.warning("缺少 pyyaml 依赖，协作指南已禁用")
        return default_config
    except Exception as e:
        logger.error(f"加载协作配置失败: {e}，协作指南已禁用")
        return default_config


def build_collaboration_guidelines(
    agents: dict[str, dict],
    available_agents: list[dict] | None = None,
    available_agents_placeholder: str | None = None,
) -> str:
    """构建协作指南

    Args:
        agents: agents 字典 {agent_name: agent_config}
        available_agents: 可选的“系统当前可用智能体列表”（通常来自 workflow 透传）。
            元素期望包含 name/description 字段。
        available_agents_placeholder: 当不希望展开列表时，用该文本替代 {available_agents}。

    Returns:
        协作指南文本，如果禁用或构建失败返回空字符串
    """
    try:
        # 加载配置
        config = load_collaboration_config()

        if not config.get("enabled", False):
            return ""

        template = config.get("guidelines_template", "")
        if not template:
            return ""

        # 构建可用 agents 列表（合并本地 discover_agents 与上游传入 available_agents）
        if available_agents_placeholder is not None:
            available_agents_text = available_agents_placeholder
        else:
            merged: dict[str, str] = {}

            # 1) 本地 agents
            for name, info in (agents or {}).items():
                if not name:
                    continue
                description = (info or {}).get("description", "Agent")
                merged[str(name)] = str(description)

            # 2) 上游可用 agents（优先覆盖本地描述）
            if available_agents:
                for agent in available_agents:
                    if not isinstance(agent, dict):
                        continue
                    name = (agent.get("name") or "").strip()
                    if not name:
                        continue
                    desc = (agent.get("description") or "Agent").strip()
                    merged[name] = desc

            agent_lines = []
            for name in sorted(merged.keys(), key=lambda s: s.lower()):
                agent_lines.append(f"- @{name}（{merged[name]}）")

            available_agents_text = "\n".join(agent_lines)

        # 替换模板变量
        guidelines = template.format(available_agents=available_agents_text)

        logger.debug(f"构建协作指南成功，包含 {len(agents)} 个 agents")
        return guidelines

    except Exception as e:
        logger.error(f"构建协作指南失败: {e}")
        return ""
