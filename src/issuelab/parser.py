"""Agent @mention 解析器：从评论中提取并映射 Agent 名称"""

import re

from issuelab.agents.registry import AGENT_NAMES


def parse_agent_mentions(comment_body: str) -> list[str]:
    """从评论中解析 @mention 并映射到 Agent 名称

    仅解析并映射 Agent 真名（不支持别名）

    Args:
        comment_body: 评论内容

    Returns:
        标准化的 Agent 名称列表
    """
    pattern = r"@([a-zA-Z_]+)"
    raw_mentions = re.findall(pattern, comment_body, re.IGNORECASE)

    # 映射到标准名称
    agents = []
    for m in raw_mentions:
        normalized = m.lower()
        if normalized in AGENT_NAMES:
            agents.append(AGENT_NAMES[normalized])

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
    return bool(re.search(r"@[a-zA-Z_]+", comment_body))
