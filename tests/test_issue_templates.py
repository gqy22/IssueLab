"""测试 GitHub Issue 模板"""

from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def test_issue_templates_directory_exists():
    """Issue 模板目录必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    assert templates_dir.exists(), f"Issue templates directory not found: {templates_dir}"


def test_paper_template_exists():
    """论文讨论模板必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    paper_template = templates_dir / "paper.yml"
    assert paper_template.exists(), f"paper.yml not found: {paper_template}"


def test_proposal_template_exists():
    """实验提案模板必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    proposal_template = templates_dir / "proposal.yml"
    assert proposal_template.exists(), f"proposal.yml not found: {proposal_template}"


def test_result_template_exists():
    """结果复盘模板必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    result_template = templates_dir / "result.yml"
    assert result_template.exists(), f"result.yml not found: {result_template}"


def test_question_template_exists():
    """科研问题模板必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    question_template = templates_dir / "question.yml"
    assert question_template.exists(), f"question.yml not found: {question_template}"
