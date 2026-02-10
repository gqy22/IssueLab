"""@ 提及策略管理模块

负责加载和应用 @mention 策略，实现集中式过滤管理。
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from issuelab.agents.registry import load_registry

logger = logging.getLogger(__name__)

# 统一的 @mention 匹配规则（支持字母、数字、下划线、连字符）
MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_-]+)")

# In-memory rate-limit state.
_RATE_LIMIT_STATE: dict[str, Any] = {
    "issue_counts": {},  # key=(username_lower, issue_number) -> count
    "hourly_events": {},  # key=username_lower -> list[datetime]
}


def load_mention_policy() -> dict[str, Any]:
    """加载 @ 提及策略配置

    Returns:
        策略配置字典

    Examples:
        >>> policy = load_mention_policy()
        >>> policy['mode']
        'permissive'
    """
    # 查找配置文件
    config_paths = [
        Path(__file__).parent.parent.parent / "config" / "mention_policy.yml",  # 项目根目录
        Path.cwd() / "config" / "mention_policy.yml",  # 当前工作目录
    ]

    config_file = None
    for path in config_paths:
        if path.exists():
            config_file = path
            break

    # 默认配置
    default_policy = {
        "blacklist": [],
        "rate_limit": {
            "enabled": False,
            "max_per_issue": 10,
            "max_per_hour": 5,
        },
    }

    if not config_file:
        logger.info("[INFO] 未找到 mention_policy.yml，使用默认配置")
        return default_policy

    # 加载 YAML 配置
    try:
        import yaml

        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config or "mention_policy" not in config:
            logger.warning("[WARN] mention_policy.yml 格式错误，使用默认配置")
            return default_policy

        policy = config["mention_policy"]

        # 合并默认配置（确保所有字段都存在）
        for key, value in default_policy.items():
            if key not in policy:
                policy[key] = value

        logger.info(f"[INFO] 加载策略配置: blacklist={policy['blacklist']}")
        return policy

    except ImportError:
        logger.error("[ERROR] 缺少 pyyaml 依赖，使用默认配置")
        return default_policy
    except Exception as e:
        logger.error(f"[ERROR] 加载配置文件失败: {e}，使用默认配置")
        return default_policy


def filter_mentions(
    mentions: list[str], policy: dict[str, Any] | None = None, issue_number: int | None = None
) -> tuple[list[str], list[str]]:
    """应用策略过滤 @mentions

    Args:
        mentions: 原始 @mentions 列表
        policy: 策略配置（None 则自动加载）

    Returns:
        (allowed_mentions, filtered_mentions) 元组
        - allowed_mentions: 允许的 @mentions
        - filtered_mentions: 被过滤的 @mentions

    Examples:
        >>> filter_mentions(['gqy20', 'github', 'spam-user'])
        (['gqy20'], ['github', 'spam-user'])
    """
    if policy is None:
        policy = load_mention_policy()

    blacklist = policy.get("blacklist", [])

    allowed = []
    filtered = []

    registry = load_registry(Path("agents"))
    allowed_agents = {name.lower() for name in registry}

    for username in mentions:
        username_lower = username.lower()

        # 0. 必须是已注册 agent
        if username_lower not in allowed_agents:
            logger.debug(f"[FILTER] 未注册 agent: {username}")
            filtered.append(username)
            continue

        # 1. 过滤黑名单
        if username_lower in [u.lower() for u in blacklist]:
            logger.debug(f"[FILTER] 黑名单: {username}")
            filtered.append(username)
            continue

        # 2. 频率限制（可选）
        if issue_number is not None and not check_rate_limit(
            username, issue_number, rate_limit_policy=policy.get("rate_limit", {})
        ):
            logger.debug(f"[FILTER] rate limit: {username}")
            filtered.append(username)
            continue

        allowed.append(username)

    logger.info(f"[FILTER] 结果: allowed={allowed}, filtered={filtered}")
    return allowed, filtered


def check_rate_limit(
    username: str,
    issue_number: int,
    rate_limit_policy: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> bool:
    """检查用户是否超过频率限制

    注意：此功能暂未实现，预留接口

    Args:
        username: 用户名
        issue_number: Issue 编号

    Returns:
        是否允许触发（True=允许）
    """
    policy = rate_limit_policy or load_mention_policy().get("rate_limit", {})
    if not bool(policy.get("enabled", False)):
        return True

    username_lower = username.lower()
    current_time = now or datetime.now(UTC)
    max_per_issue = int(policy.get("max_per_issue", 10))
    max_per_hour = int(policy.get("max_per_hour", 5))

    issue_key = (username_lower, int(issue_number))
    issue_counts: dict[tuple[str, int], int] = _RATE_LIMIT_STATE.setdefault("issue_counts", {})
    count_on_issue = issue_counts.get(issue_key, 0)
    if count_on_issue >= max_per_issue:
        return False

    hourly_events: dict[str, list[datetime]] = _RATE_LIMIT_STATE.setdefault("hourly_events", {})
    user_events = hourly_events.get(username_lower, [])
    window_start = current_time - timedelta(hours=1)
    user_events = [t for t in user_events if t >= window_start]
    if len(user_events) >= max_per_hour:
        hourly_events[username_lower] = user_events
        return False

    issue_counts[issue_key] = count_on_issue + 1
    user_events.append(current_time)
    hourly_events[username_lower] = user_events
    return True


def extract_mentions(text: str) -> list[str]:
    """从文本中提取所有@mentions（去重，保留顺序）"""
    if not text:
        return []

    matches = MENTION_PATTERN.findall(text)
    # 过滤纯数字（GitHub 用户名不能是纯数字）
    matches = [m for m in matches if not m.isdigit()]

    # 去重并保持顺序
    return list(dict.fromkeys(matches))


def rank_mentions_by_frequency(text: str) -> list[str]:
    """按出现次数排序 @mentions（次数降序，首次出现位置升序）"""
    if not text:
        return []

    matches = MENTION_PATTERN.findall(text)
    matches = [m for m in matches if not m.isdigit()]
    if not matches:
        return []

    counts: dict[str, int] = {}
    first_index: dict[str, int] = {}
    canonical: dict[str, str] = {}

    for idx, mention in enumerate(matches):
        key = mention.lower()
        counts[key] = counts.get(key, 0) + 1
        if key not in first_index:
            first_index[key] = idx
            canonical[key] = mention

    ordered_keys = sorted(counts.keys(), key=lambda k: (-counts[k], first_index[k]))
    return [canonical[k] for k in ordered_keys]


def clean_mentions_in_text(text: str, replacement: str = "用户 {username}") -> str:
    """清理文本中的所有 @mentions"""
    if not text:
        return text

    def replace_fn(match: re.Match) -> str:
        username = match.group(1)
        if username.isdigit():
            return match.group(0)
        return replacement.format(username=username)

    return MENTION_PATTERN.sub(replace_fn, text)


def build_mention_section(mentions: list[str], format_type: str = "labeled") -> str:
    """构建 @ 区域"""
    if not mentions:
        return ""

    if format_type == "labeled":
        return f"---\n相关人员: {' '.join(f'@{m}' for m in mentions)}"
    if format_type == "simple":
        return f"---\n{' '.join(f'@{m}' for m in mentions)}"
    if format_type == "list":
        items = "\n".join(f"- @{m}" for m in mentions)
        return f"---\n协作请求:\n{items}"
    return f"---\n相关人员: {' '.join(f'@{m}' for m in mentions)}"
