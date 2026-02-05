"""@ 提及策略管理模块

负责加载和应用 @mention 策略，实现集中式过滤管理。
"""

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 统一的 @mention 匹配规则（支持字母、数字、下划线、连字符）
MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_-]+)")


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
        "mode": "permissive",
        "system_accounts": ["github", "github-actions", "dependabot"],
        "blacklist": [],
        "whitelist": [],
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

        logger.info(f"[INFO] 加载策略配置: mode={policy['mode']}, blacklist={policy['blacklist']}")
        return policy

    except ImportError:
        logger.error("[ERROR] 缺少 pyyaml 依赖，使用默认配置")
        return default_policy
    except Exception as e:
        logger.error(f"[ERROR] 加载配置文件失败: {e}，使用默认配置")
        return default_policy


def filter_mentions(mentions: list[str], policy: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
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

    mode = policy.get("mode", "permissive")
    system_accounts = policy.get("system_accounts", [])
    blacklist = policy.get("blacklist", [])
    whitelist = policy.get("whitelist", [])

    allowed = []
    filtered = []

    for username in mentions:
        username_lower = username.lower()

        # 1. 过滤系统账号
        if username_lower in [acc.lower() for acc in system_accounts]:
            logger.debug(f"[FILTER] 系统账号: {username}")
            filtered.append(username)
            continue

        # 2. 过滤黑名单
        if username_lower in [u.lower() for u in blacklist]:
            logger.debug(f"[FILTER] 黑名单: {username}")
            filtered.append(username)
            continue

        # 3. 根据模式判断
        if mode == "strict":
            # strict 模式：只允许白名单
            if username_lower in [u.lower() for u in whitelist]:
                allowed.append(username)
            else:
                logger.debug(f"[FILTER] 不在白名单: {username}")
                filtered.append(username)
        else:
            # permissive 模式：默认允许（已过滤系统账号和黑名单）
            allowed.append(username)

    logger.info(f"[FILTER] 结果: allowed={allowed}, filtered={filtered}")
    return allowed, filtered


def check_rate_limit(username: str, issue_number: int) -> bool:
    """检查用户是否超过频率限制

    注意：此功能暂未实现，预留接口

    Args:
        username: 用户名
        issue_number: Issue 编号

    Returns:
        是否允许触发（True=允许）
    """
    # TODO: 实现频率限制逻辑
    # 需要持久化存储（如 Redis 或本地文件）
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
