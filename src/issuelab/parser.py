"""Agent @mention 解析器：从评论中提取并映射 Agent 名称"""

import re

# Agent 别名映射表
AGENT_ALIASES = {
    # Moderator 变体
    "moderator": "moderator",
    "mod": "moderator",
    # ReviewerA 变体
    "reviewer": "reviewer_a",
    "reviewera": "reviewer_a",
    "reviewer_a": "reviewer_a",
    "reva": "reviewer_a",
    # ReviewerB 变体
    "reviewerb": "reviewer_b",
    "reviewer_b": "reviewer_b",
    "revb": "reviewer_b",
    # Summarizer 变体
    "summarizer": "summarizer",
    "summary": "summarizer",
}


def parse_agent_mentions(comment_body: str) -> list[str]:
    """从评论中解析 @mention 并映射到 Agent 名称

    专用于解析和转换 Agent 别名（如 @mod -> moderator）

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
        if normalized in AGENT_ALIASES:
            agents.append(AGENT_ALIASES[normalized])

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


# 向后兼容的别名（逐步废弃）
parse_mentions = parse_agent_mentions
has_mentions = has_agent_mentions
