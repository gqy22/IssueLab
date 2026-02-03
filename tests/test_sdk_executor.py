"""测试 SDK 执行器"""

from issuelab.sdk_executor import (
    create_agent_options,
    discover_agents,
    load_prompt,
    parse_observer_response,
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


class TestParseObserverResponse:
    """测试 Observer 响应解析"""

    def test_parse_yaml_block_scalar_trigger(self):
        """测试 YAML 块标量格式 - 触发场景"""
        response = """```yaml
analysis: |
  Issue #123 是一个新论文讨论，包含 arXiv 链接和论文模板

should_trigger: true

agent: moderator

comment: |
  @Moderator 请分诊这篇论文，它包含 arXiv 链接和模板

reason: |
  Issue #123 包含论文模板和 arXiv 链接，需要分诊决定后续评审流程
```"""
        result = parse_observer_response(response, 123)
        assert result["should_trigger"] is True
        assert result["agent"] == "moderator"
        assert "@Moderator" in result["comment"]
        assert "分诊" in result["reason"]
        assert "arXiv" in result["analysis"]

    def test_parse_yaml_block_scalar_skip(self):
        """测试 YAML 块标量格式 - 跳过场景"""
        response = """```yaml
analysis: |
  Issue #456 是一个技术问题，已有 @ReviewerA 进行分析

should_trigger: false

reason: |
  该 Issue 已有合适的 Agent 参与，无需重复触发
```"""
        result = parse_observer_response(response, 456)
        assert result["should_trigger"] is False
        assert "已有" in result["reason"]

    def test_parse_fallback_line_format(self):
        """测试回退行扫描格式"""
        response = """
analysis: 简单分析
should_trigger: true
agent: reviewer_a
comment: @ReviewerA 评审
reason: 简单原因
"""
        result = parse_observer_response(response, 1)
        assert result["should_trigger"] is True
        assert result["agent"] == "reviewer_a"
        assert "@ReviewerA" in result["comment"]

    def test_parse_no_yaml_codeblock(self):
        """测试纯文本格式（无代码块）"""
        response = """Issue Analysis:
这是一个论文讨论

should_trigger: true
agent: reviewer_b

comment: @ReviewerB 请找问题"""
        result = parse_observer_response(response, 2)
        assert result["should_trigger"] is True
        assert result["agent"] == "reviewer_b"

    def test_parse_empty_response(self):
        """测试空响应"""
        result = parse_observer_response("", 1)
        assert result["should_trigger"] is False
        assert result["agent"] == ""
        assert result["comment"] == ""

    def test_parse_default_comment(self):
        """测试默认触发评论"""
        response = """```yaml
analysis: 测试

should_trigger: true

agent: summarizer
```"""
        result = parse_observer_response(response, 1)
        assert result["should_trigger"] is True
        assert result["agent"] == "summarizer"
        assert "@Summarizer" in result["comment"]
