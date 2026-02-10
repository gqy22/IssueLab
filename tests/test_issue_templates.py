"""测试 GitHub Issue 模板"""

from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def test_issue_templates_directory_exists():
    """Issue 模板目录必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    assert templates_dir.exists(), f"Issue templates directory not found: {templates_dir}"


@pytest.mark.parametrize("template_name", ["paper.yml", "proposal.yml", "result.yml", "question.yml"])
def test_required_templates_exist(template_name: str):
    """核心模板文件必须存在"""
    templates_dir = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE"
    template_path = templates_dir / template_name
    assert template_path.exists(), f"{template_name} not found: {template_path}"
