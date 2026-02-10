"""测试系统智能体提示词加载（agents 单源）"""

from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def _prompt_path(agent_name: str) -> Path:
    return AGENTS_DIR / agent_name / "prompt.md"


def test_agents_directory_exists():
    """agents 目录必须存在"""
    assert AGENTS_DIR.exists(), f"agents directory not found: {AGENTS_DIR}"


def test_prompts_not_empty():
    """所有提示词文件必须非空"""
    prompt_agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
    for agent in prompt_agents:
        prompt_path = _prompt_path(agent)
        assert prompt_path.exists(), f"{agent}/prompt.md not found: {prompt_path}"
        content = prompt_path.read_text()
        assert len(content) > 50, f"{agent}/prompt.md is too short or empty"


def test_prompts_contain_role_definition():
    """提示词必须包含角色定义"""
    # Moderator 应该包含 "Moderator" 或 "moderator"
    moderator = _prompt_path("moderator").read_text()
    assert "Moderator" in moderator or "moderator" in moderator

    # ReviewerA 应该包含 "Reviewer" 或 "reviewer"
    reviewer_a = _prompt_path("reviewer_a").read_text()
    assert "Reviewer" in reviewer_a or "reviewer" in reviewer_a

    # ReviewerB 应该包含 "Reviewer" 或 "reviewer"
    reviewer_b = _prompt_path("reviewer_b").read_text()
    assert "Reviewer" in reviewer_b or "reviewer" in reviewer_b

    # Summarizer 应该包含 "Summarizer" 或 "summarizer"
    summarizer = _prompt_path("summarizer").read_text()
    assert "Summarizer" in summarizer or "summarizer" in summarizer
