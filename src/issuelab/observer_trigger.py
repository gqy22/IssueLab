"""
Observer 自动触发功能

实现Observer自动触发agent的核心逻辑：
- 系统agent通过workflow dispatch触发（使用 GitHub App token）
- 用户agent通过repository/workflow dispatch触发（使用 GitHub App token）

统一使用dispatch机制，无需预创建labels，简化架构。
"""

import logging
import os
import subprocess

from issuelab.agents.registry import is_registered_agent
from issuelab.agents.registry import is_system_agent as registry_is_system_agent

logger = logging.getLogger(__name__)


def is_system_agent(agent_name: str) -> bool:
    """
    判断是否是系统agent

    Args:
        agent_name: Agent名称

    Returns:
        True: 系统agent
        False: 用户agent
    """
    if not agent_name:
        return False
    is_system, _ = registry_is_system_agent(agent_name)
    return is_system


def trigger_system_agent(agent_name: str, issue_number: int) -> bool:
    """
    触发系统agent（通过workflow dispatch）

    Args:
        agent_name: Agent名称
        issue_number: Issue编号

    Returns:
        True: 触发成功
        False: 触发失败
    """
    try:
        subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                "agent.yml",
                "-f",
                f"agent={agent_name.lower()}",
                "-f",
                f"issue_number={issue_number}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"[OK] 已触发 workflow agent.yml: agent={agent_name}, issue=#{issue_number}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"[ERROR] 触发workflow失败: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"[ERROR] 触发系统agent失败: {e}")
        return False


def trigger_user_agent(username: str, issue_number: int, issue_title: str, issue_body: str) -> bool:
    """
    触发用户agent（通过dispatch系统或本地执行）

    逻辑：
    - 如果是本地仓库（repository == source_repo）：本地执行
    - 如果是fork仓库：dispatch到用户fork

    Args:
        username: 用户名
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容

    Returns:
        True: 触发成功
        False: 触发失败
    """
    # 获取当前仓库信息
    source_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not source_repo:
        logger.error("[ERROR] GITHUB_REPOSITORY environment variable not set")
        return False

    # 读取agent配置
    is_registered, config = is_registered_agent(username)
    if not is_registered or not config:
        logger.error(f"[ERROR] Agent {username} not registered or disabled")
        return False

    # 统一走 dispatch 到用户仓库
    return dispatch_user_agent(username, issue_number, issue_title, issue_body, source_repo)


def dispatch_user_agent(username: str, issue_number: int, issue_title: str, issue_body: str, source_repo: str) -> bool:
    """Dispatch用户agent到fork仓库"""
    try:
        from issuelab.cli.dispatch import dispatch_mentions

        summary = dispatch_mentions(
            mentions=[username],
            agents_dir="agents",
            source_repo=source_repo,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            app_id=os.environ.get("GITHUB_APP_ID"),
            app_private_key=os.environ.get("GITHUB_APP_PRIVATE_KEY"),
        )
        if summary.get("success_count", 0) > 0:
            logger.info(f"[OK] 已dispatch用户agent: {username} for #{issue_number}")
            return True
        logger.error(f"[ERROR] dispatch用户agent失败: {username} (summary={summary})")
        return False

    except Exception as e:
        logger.error(f"[ERROR] dispatch用户agent异常: {e}")
        return False


def auto_trigger_agent(agent_name: str, issue_number: int, issue_title: str, issue_body: str) -> bool:
    """
    根据agent类型自动选择触发方式

    Args:
        agent_name: Agent名称
        issue_number: Issue编号
        issue_title: Issue标题
        issue_body: Issue内容

    Returns:
        True: 触发成功
        False: 触发失败
    """
    if is_system_agent(agent_name):
        return trigger_system_agent(agent_name, issue_number)
    elif is_registered_agent(agent_name)[0]:
        return trigger_user_agent(agent_name, issue_number, issue_title, issue_body)
    else:
        logger.warning(
            f"[WARNING] Agent '{agent_name}' 不是系统 agent 也未注册，跳过触发。 "
            f"Issue #{issue_number} 的 observer 可能输出了无效的 agent 名称。"
        )
        return False


def process_observer_results(results: list[dict], issue_data: dict[int, dict], auto_trigger: bool = True) -> int:
    """
    处理Observer批量分析结果，自动触发agent

    Args:
        results: Observer分析结果列表
        issue_data: Issue数据字典 {issue_number: {title, body}}
        auto_trigger: 是否自动触发

    Returns:
        成功触发的agent数量
    """
    if not auto_trigger:
        return 0

    triggered_count = 0

    for result in results:
        if not result.get("should_trigger", False):
            continue

        issue_number = result["issue_number"]
        agent_name = result.get("agent")

        if not agent_name:
            logger.warning(f"[WARNING] Issue #{issue_number} 缺少agent名称")
            continue

        if issue_number not in issue_data:
            logger.warning(f"[WARNING] Issue #{issue_number} 缺少数据")
            continue

        issue = issue_data[issue_number]
        success = auto_trigger_agent(
            agent_name=agent_name,
            issue_number=issue_number,
            issue_title=issue.get("title", ""),
            issue_body=issue.get("body", ""),
        )

        if success:
            triggered_count += 1

    logger.info(f"[INFO] 总计触发 {triggered_count} 个agent")
    return triggered_count
