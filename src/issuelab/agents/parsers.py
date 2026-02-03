"""响应解析工具

解析 Agent 响应（YAML 格式）。
"""

from issuelab.logging_config import get_logger

logger = get_logger(__name__)


def parse_observer_response(response: str, issue_number: int | None = None) -> dict:
    """解析 Observer Agent 的响应

    Args:
        response: Agent 响应文本（YAML 格式）
        issue_number: Issue 编号（可选，用于日志记录）

    Returns:
        解析后的决策结果 {
            "should_trigger": bool,
            "agent": str,
            "comment": str,
            "reason": str,
            "analysis": str,
        }
    """
    # 如果提供了 issue_number，记录日志
    if issue_number is not None:
        logger.debug(f"解析 Issue #{issue_number} 的 Observer 响应")

    result = {
        "should_trigger": False,
        "agent": "",
        "comment": "",
        "reason": "",
        "analysis": "",
    }

    yaml_data = _try_parse_yaml(response)
    if yaml_data is None:
        return result

    result["should_trigger"] = yaml_data.get("should_trigger", False)
    result["agent"] = yaml_data.get("agent", "") or yaml_data.get("trigger_agent", "")
    result["comment"] = yaml_data.get("comment", "") or yaml_data.get("trigger_comment", "")
    result["reason"] = yaml_data.get("reason", "") or yaml_data.get("skip_reason", "")
    result["analysis"] = yaml_data.get("analysis", "")

    # 如果没有解析到触发评论，使用默认格式
    if result["should_trigger"] and result["agent"] and not result["comment"]:
        result["comment"] = _get_default_trigger_comment(result["agent"])

    return result


def _try_parse_yaml(response: str) -> dict | None:
    """尝试解析 YAML 格式的响应

    Args:
        response: Agent 响应文本

    Returns:
        解析后的字典，失败返回 None
    """
    import yaml

    # 清理响应文本
    text = response.strip()

    # 检查是否包含 YAML 代码块标记
    if "```yaml" in text:
        # 提取 ```yaml 和 ``` 之间的内容
        start = text.find("```yaml")
        if start == -1:
            start = text.find("```")
        end = text.rfind("```")
        if start != -1 and end != -1 and end > start:
            # 找到代码块内容（跳过 ```yaml 行和 ``` 行）
            lines = text[start:end].split("\n")
            if len(lines) >= 2:
                yaml_content = "\n".join(lines[1:])
                try:
                    return yaml.safe_load(yaml_content)
                except yaml.YAMLError:
                    pass
    elif text.startswith("---"):
        # 可能直接是 YAML 文档
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            pass

    # 检查是否是简单的键值对格式（每行一个）
    lines = text.split("\n")
    yaml_like = True
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            yaml_like = False
            break

    if yaml_like:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            pass

    return None


def parse_papers_recommendation(response: str, paper_count: int) -> list[dict]:
    """解析 Observer 对论文推荐的响应

    Args:
        response: Agent 响应文本（YAML 格式）
        paper_count: 原始论文数量（用于验证 index）

    Returns:
        推荐论文列表 [{
            "index": int,
            "title": str,
            "reason": str,
            "summary": str,
            "category": str,
            "url": str,
            "pdf_url": str,
            "authors": str,
            "published": str,
        }]
    """
    recommended = []

    yaml_data = _try_parse_yaml(response)
    if yaml_data is None:
        logger.warning("无法解析论文推荐结果")
        return recommended

    # 解析 recommended 列表
    rec_list = yaml_data.get("recommended", [])
    if not rec_list:
        # 尝试从 analysis 中提取信息
        logger.warning("响应中未找到 recommended 字段")
        return recommended

    for item in rec_list:
        if not isinstance(item, dict):
            continue

        index = item.get("index", -1)
        if index < 0 or index >= paper_count:
            continue

        recommended.append(
            {
                "index": index,
                "title": item.get("title", ""),
                "reason": item.get("reason", ""),
                "summary": item.get("summary", ""),
                # 以下字段需要从原始论文数据中获取
                "category": "",
                "url": "",
                "pdf_url": "",
                "authors": "",
                "published": "",
            }
        )

    logger.info(f"解析到 {len(recommended)} 篇推荐论文")
    return recommended


def _get_default_trigger_comment(agent: str) -> str:
    """获取默认的触发评论

    Args:
        agent: Agent 名称

    Returns:
        默认的触发评论
    """
    agent_map = {
        "moderator": "@moderator 请审核",
        "reviewer_a": "@reviewer_a 评审",
        "reviewer_b": "@reviewer_b 找问题",
        "summarizer": "@summarizer 汇总",
        "observer": "@observer",
    }
    return agent_map.get(agent, f"@{agent}")
