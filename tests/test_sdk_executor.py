"""测试 SDK 执行器"""

from issuelab.sdk_executor import (
    create_agent_options,
    discover_agents,
    load_prompt,
)


def test_discover_agents_returns_dict():
    """discover_agents 应该返回字典"""
    agents = discover_agents()
    assert isinstance(agents, dict)
    assert len(agents) > 0


def test_create_agent_options_has_agents():
    """create_agent_options 应该包含所有定义的代理（observer除外）"""
    options = create_agent_options()
    assert hasattr(options, "agents")
    assert "moderator" in options.agents
    assert "reviewer_a" in options.agents
    assert "reviewer_b" in options.agents
    assert "summarizer" in options.agents
    # observer 不在此列表中（单独处理）
    assert "observer" not in options.agents


def test_create_agent_options_has_setting_sources():
    """create_agent_options 应该设置 setting_sources"""
    options = create_agent_options()
    assert hasattr(options, "setting_sources")
    assert "user" in options.setting_sources
    assert "project" in options.setting_sources


def test_load_prompt_moderator():
    """load_prompt 应该加载 moderator 提示词"""
    result = load_prompt("moderator")
    assert "Moderator" in result or "分诊" in result
    assert len(result) > 0


def test_load_prompt_unknown_agent():
    """load_prompt 对未知代理返回空"""
    result = load_prompt("unknown_agent_that_does_not_exist")
    assert result == ""
