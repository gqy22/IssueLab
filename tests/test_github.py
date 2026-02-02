"""测试 GitHub 工具"""

from unittest.mock import MagicMock, patch

from issuelab.tools.github import get_issue_info, post_comment, update_label


def test_get_issue_info():
    """测试获取 Issue 信息"""
    # Mock gh 命令返回
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"number":1,"title":"测试 Issue","body":"内容","labels":[{"name":"bug"}]}'
        )

        result = get_issue_info(1)

        assert result["number"] == 1
        assert result["title"] == "测试 Issue"
        mock_run.assert_called_once()


def test_post_comment():
    """测试发布评论"""
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = post_comment(1, "测试评论")

        assert "Comment posted" in result
        mock_run.assert_called_once()


def test_update_label():
    """测试更新标签"""
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = update_label(1, "bug", action="add")

        assert "Label 'bug' added" in result
        mock_run.assert_called_once()
