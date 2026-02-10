"""测试 GitHub Actions 工作流配置"""

from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def test_workflow_file_exists():
    """工作流文件必须存在"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    assert workflow_path.exists(), f"Workflow file not found: {workflow_path}"


def test_dispatch_workflow_only_handles_issues_event():
    """dispatch_agents workflow 应仅处理 issues 事件，避免与 orchestrator 评论触发重叠。"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "dispatch_agents.yml"
    content = workflow_path.read_text()

    assert "on:" in content
    assert "issues:" in content
    assert "issue_comment:" not in content


def test_workflow_has_issue_comment_trigger():
    """工作流必须定义 issue_comment 触发器"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "issue_comment" in content, "Missing issue_comment trigger"
    assert "created" in content or "edited" in content, "Missing issue_comment types"


def test_workflow_has_concurrency():
    """工作流必须定义并发控制"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "concurrency" in content, "Missing concurrency configuration"
    assert "github.event.issue.number" in content, "Concurrency should use issue number"


def test_workflow_uses_uv():
    """工作流应该使用 uv"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "uv" in content, "Workflow should use uv for package management"


def test_workflow_uses_required_model_secrets():
    """orchestrator 应包含模型运行必需的 secrets。"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "ANTHROPIC_AUTH_TOKEN" in content, "Workflow should use ANTHROPIC_AUTH_TOKEN secret"
    assert "PAT_TOKEN" in content, "Workflow should use PAT_TOKEN secret for gh writes"


def test_workflow_has_permissions():
    """工作流应该定义 permissions"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()

    assert "permissions:" in content or "issues: write" in content, "Should define permissions"


def test_orchestrator_workflow_has_timeout_and_uv_cache():
    """orchestrator 应同时具备 timeout 与 uv cache。"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"
    content = workflow_path.read_text()
    assert "timeout-minutes:" in content, "工作流应该设置 timeout-minutes"
    assert "enable-cache: true" in content, "工作流应该启用 uv 缓存"


def test_orchestrator_workflow_sets_skip_version_check():
    """orchestrator.yml 应该设置 CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "orchestrator.yml"

    if not workflow_path.exists():
        pytest.skip("工作流文件不存在")

    content = workflow_path.read_text()
    assert (
        "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK" in content
    ), "工作流应该设置 CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK 环境变量"
