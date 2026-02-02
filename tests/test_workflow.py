"""测试 GitHub Actions 工作流配置"""
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def test_workflow_file_exists():
    """工作流文件必须存在"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    assert workflow_path.exists(), f"Workflow file not found: {workflow_path}"


def test_workflow_has_issue_comment_trigger():
    """工作流必须定义 issue_comment 触发器"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "issue_comment" in content, "Missing issue_comment trigger"
    assert "created" in content or "edited" in content, "Missing issue_comment types"


def test_workflow_has_issues_trigger():
    """工作流必须定义 issues 触发器"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "issues:" in content, "Missing issues trigger"
    assert "labeled" in content, "Missing issues labeled type"


def test_workflow_has_concurrency():
    """工作流必须定义并发控制"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "concurrency" in content, "Missing concurrency configuration"
    assert "github.event.issue.number" in content, "Concurrency should use issue number"


def test_workflow_has_jobs():
    """工作流必须包含 jobs"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "jobs:" in content, "Missing jobs configuration"


def test_workflow_uses_uv():
    """工作流应该使用 uv"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "uv" in content, "Workflow should use uv for package management"


def test_workflow_uses_correct_secrets():
    """工作流应该使用正确的 Secret 名称"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    # 检查用户配置的 Secret
    assert "ANTHROPIC_API_KEY" in content, "Workflow should use ANTHROPIC_API_KEY secret"
    assert "ANTHROPIC_BASE_URL" in content, "Workflow should use ANTHROPIC_BASE_URL secret"
    assert "ANTHROPIC_MODEL" in content, "Workflow should use ANTHROPIC_MODEL secret"


def test_workflow_runs_on_ubuntu():
    """工作流应该在 ubuntu 运行"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "runs-on: ubuntu-latest" in content, "Should run on ubuntu-latest"


def test_workflow_has_permissions():
    """工作流应该定义 permissions"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "permissions:" in content or "issues: write" in content, "Should define permissions"
