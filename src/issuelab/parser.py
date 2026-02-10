"""Agent @mention 解析器：从评论中提取并映射 Agent 名称"""

from pathlib import Path

from issuelab.agents.registry import load_registry
from issuelab.utils.mentions import GITHUB_MENTION_PATTERN, extract_github_mentions


def parse_agent_mentions(comment_body: str) -> list[str]:
    """从评论中解析 @mention 并映射到 Agent 名称

    仅解析并映射 Agent 真名（不支持别名）

    Args:
        comment_body: 评论内容

    Returns:
        标准化的 Agent 名称列表
    """
    raw_mentions = extract_github_mentions(comment_body)

    registry = load_registry(Path("agents"), include_disabled=False)
    registry_lc = {str(name).lower(): cfg for name, cfg in registry.items()}

    # 映射到标准名称（仅允许已注册 agent）
    agents = []
    for m in raw_mentions:
        normalized = m.lower()
        config = registry_lc.get(normalized)
        if config is None:
            continue
        canonical = config.get("owner") or config.get("username") or normalized
        agents.append(str(canonical).lower())

    # 去重，保持顺序
    seen = set()
    unique_agents = []
    for a in agents:
        if a not in seen:
            seen.add(a)
            unique_agents.append(a)

    return unique_agents


def has_agent_mentions(comment_body: str) -> bool:
    """检查评论是否包含 Agent @mention

    Args:
        comment_body: 评论内容

    Returns:
        是否包含 @mention
    """
    return bool(GITHUB_MENTION_PATTERN.search(comment_body))
