"""轻量集成测试 - 验证核心模块协作。"""

from issuelab.agents import discover_agents, load_prompt, normalize_agent_name
from issuelab.parser import parse_agent_mentions


def test_parser_agent_integration():
    """测试 parser 和 agents 模块的集成"""
    # 解析 @mention
    comment = "@moderator please review @reviewer_a @reviewer_b"
    agents = parse_agent_mentions(comment)

    # 验证所有解析的 agent 都存在
    discovered = discover_agents()
    for agent in agents:
        assert agent in discovered, f"Agent {agent} not found in discovered agents"


def test_end_to_end_agent_loading():
    """端到端测试：从名称到加载 prompt"""
    # 使用真名
    name = "moderator"

    # 1. 标准化
    normalized = normalize_agent_name(name)
    assert normalized == "moderator"

    # 2. 加载 prompt
    prompt = load_prompt(normalized)
    assert len(prompt) > 0
    assert "Moderator" in prompt or "审核" in prompt


def test_all_prompts_loadable():
    """验证所有发现的 agent 都能正确加载 prompt（跨 discovery + load_prompt）。"""
    agents = discover_agents()

    for agent_name in agents:
        prompt = load_prompt(agent_name)
        assert len(prompt) > 0, f"Agent {agent_name} has empty prompt"
        assert not prompt.startswith("---"), f"Agent {agent_name} prompt should be plain markdown"
