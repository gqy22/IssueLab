"""测试提示词模板加载"""
from pathlib import Path

# 提示词目录在项目根目录
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def test_prompts_directory_exists():
    """提示词目录必须存在"""
    assert PROMPTS_DIR.exists(), f"prompts directory not found: {PROMPTS_DIR}"


def test_moderator_prompt_exists():
    """Moderator 提示词必须存在"""
    moderator_prompt = PROMPTS_DIR / "moderator.md"
    assert moderator_prompt.exists(), f"moderator.md not found: {moderator_prompt}"


def test_reviewer_a_prompt_exists():
    """ReviewerA 提示词必须存在"""
    reviewer_a_prompt = PROMPTS_DIR / "reviewer_a.md"
    assert reviewer_a_prompt.exists(), f"reviewer_a.md not found: {reviewer_a_prompt}"


def test_reviewer_b_prompt_exists():
    """ReviewerB 提示词必须存在"""
    reviewer_b_prompt = PROMPTS_DIR / "reviewer_b.md"
    assert reviewer_b_prompt.exists(), f"reviewer_b.md not found: {reviewer_b_prompt}"


def test_summarizer_prompt_exists():
    """Summarizer 提示词必须存在"""
    summarizer_prompt = PROMPTS_DIR / "summarizer.md"
    assert summarizer_prompt.exists(), f"summarizer.md not found: {summarizer_prompt}"


def test_prompts_not_empty():
    """所有提示词文件必须非空"""
    prompt_files = ["moderator.md", "reviewer_a.md", "reviewer_b.md", "summarizer.md"]
    for pf in prompt_files:
        prompt_path = PROMPTS_DIR / pf
        content = prompt_path.read_text()
        assert len(content) > 50, f"{pf} is too short or empty"


def test_prompts_contain_role_definition():
    """提示词必须包含角色定义"""
    # Moderator 应该包含 "Moderator" 或 "moderator"
    moderator = (PROMPTS_DIR / "moderator.md").read_text()
    assert "Moderator" in moderator or "moderator" in moderator

    # ReviewerA 应该包含 "Reviewer" 或 "reviewer"
    reviewer_a = (PROMPTS_DIR / "reviewer_a.md").read_text()
    assert "Reviewer" in reviewer_a or "reviewer" in reviewer_a

    # ReviewerB 应该包含 "Reviewer" 或 "reviewer"
    reviewer_b = (PROMPTS_DIR / "reviewer_b.md").read_text()
    assert "Reviewer" in reviewer_b or "reviewer" in reviewer_b

    # Summarizer 应该包含 "Summarizer" 或 "summarizer"
    summarizer = (PROMPTS_DIR / "summarizer.md").read_text()
    assert "Summarizer" in summarizer or "summarizer" in summarizer
