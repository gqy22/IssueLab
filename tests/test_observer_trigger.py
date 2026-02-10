"""
测试 Observer 自动触发功能

TDD 测试用例：
1. 判断系统agent
2. 触发系统agent（通过workflow dispatch）
3. 触发用户agent（通过dispatch）
4. observe-batch 集成测试
"""

import subprocess
from unittest.mock import Mock, patch

import pytest


class TestSystemAgentDetection:
    """测试系统agent检测"""

    @pytest.mark.parametrize(
        ("agent_name", "expected"),
        [
            ("moderator", True),
            ("reviewer_a", True),
            ("observer", True),
            ("Moderator", True),
            ("REVIEWER_A", True),
            ("gqy22", False),
            ("alice", False),
            ("", False),
        ],
    )
    def test_is_system_agent_cases(self, agent_name: str, expected: bool):
        """系统agent识别应正确处理大小写、空值与用户agent"""
        from issuelab.observer_trigger import is_system_agent

        assert is_system_agent(agent_name) is expected


class TestSystemAgentTrigger:
    """测试系统agent触发"""

    @patch("subprocess.run")
    def test_trigger_system_agent_dispatches_workflow(self, mock_run):
        """触发系统agent应该通过workflow dispatch触发"""
        from issuelab.observer_trigger import trigger_system_agent

        mock_run.return_value = Mock(returncode=0)

        trigger_system_agent("moderator", 42)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "workflow" in call_args
        assert "run" in call_args
        assert "agent.yml" in call_args
        assert "-f" in call_args
        assert "agent=moderator" in call_args
        assert "issue_number=42" in call_args

    @patch("subprocess.run")
    def test_trigger_system_agent_returns_true_on_success(self, mock_run):
        """成功触发应该返回True"""
        from issuelab.observer_trigger import trigger_system_agent

        mock_run.return_value = Mock(returncode=0)

        result = trigger_system_agent("observer", 1)

        assert result is True

    @patch("subprocess.run")
    def test_trigger_system_agent_returns_false_on_failure(self, mock_run):
        """触发失败应该返回False"""
        from issuelab.observer_trigger import trigger_system_agent

        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")

        result = trigger_system_agent("observer", 1)

        assert result is False

    @patch("subprocess.run")
    def test_trigger_multiple_system_agents(self, mock_run):
        """可以触发多个不同的系统agent"""
        from issuelab.observer_trigger import trigger_system_agent

        mock_run.return_value = Mock(returncode=0)

        trigger_system_agent("moderator", 1)
        trigger_system_agent("reviewer_a", 2)
        trigger_system_agent("observer", 3)

        assert mock_run.call_count == 3


class TestUserAgentTrigger:
    """测试用户agent触发"""

    @patch("issuelab.cli.dispatch.dispatch_mentions")
    def test_trigger_user_agent_calls_dispatch(self, mock_dispatch, monkeypatch):
        """触发用户agent应该调用dispatch系统"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = {"success_count": 1}

        result = trigger_user_agent(username="gqy22", issue_number=42, issue_title="Test Issue", issue_body="Test body")

        mock_dispatch.assert_called_once()
        assert result is True

    @patch("issuelab.cli.dispatch.dispatch_mentions")
    def test_trigger_user_agent_with_correct_params(self, mock_dispatch, monkeypatch):
        """触发用户agent应该传递正确的参数"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = {"success_count": 1}

        # 使用已注册的 agent gqy22
        trigger_user_agent(username="gqy22", issue_number=123, issue_title="Bug Report", issue_body="Description")

        # 验证dispatch被正确调用
        mock_dispatch.assert_called_once()

    @patch("issuelab.cli.dispatch.dispatch_mentions")
    def test_trigger_user_agent_returns_false_on_failure(self, mock_dispatch, monkeypatch):
        """dispatch失败应该返回False"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = {"success_count": 0}  # 失败

        result = trigger_user_agent(username="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False

    @patch("issuelab.cli.dispatch.dispatch_mentions")
    def test_trigger_user_agent_handles_exception(self, mock_dispatch, monkeypatch):
        """dispatch异常应该被处理并返回False"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.side_effect = Exception("Dispatch error")

        result = trigger_user_agent(username="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False

    @patch("issuelab.cli.dispatch.dispatch_mentions")
    def test_dispatch_user_agent_does_not_mutate_sys_argv(self, mock_dispatch):
        """dispatch_user_agent 不应修改全局 sys.argv"""
        import sys

        from issuelab.observer_trigger import dispatch_user_agent

        mock_dispatch.return_value = {"success_count": 1}
        before = list(sys.argv)
        dispatch_user_agent("gqy22", 1, "T", "B", "owner/repo")
        after = list(sys.argv)
        assert after == before


class TestObserverAutoTrigger:
    """测试Observer自动触发集成"""

    @patch("issuelab.observer_trigger.trigger_system_agent")
    @patch("issuelab.observer_trigger.is_system_agent")
    def test_auto_trigger_system_agent(self, mock_is_system, mock_trigger_system):
        """Observer判断需要触发系统agent时应发起workflow dispatch"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_system.return_value = True
        mock_trigger_system.return_value = True

        result = auto_trigger_agent(agent_name="moderator", issue_number=1, issue_title="Test", issue_body="Body")

        mock_trigger_system.assert_called_once_with("moderator", 1)
        assert result is True

    @patch("issuelab.observer_trigger.trigger_user_agent")
    @patch("issuelab.observer_trigger.is_system_agent")
    def test_auto_trigger_user_agent(self, mock_is_system, mock_trigger_user):
        """Observer判断需要触发用户agent时应该调用dispatch"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_system.return_value = False
        mock_trigger_user.return_value = True

        result = auto_trigger_agent(agent_name="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        # trigger_user_agent使用位置参数，不是关键字参数
        mock_trigger_user.assert_called_once_with("gqy22", 1, "Test", "Body")
        assert result is True

    @patch("issuelab.observer_trigger.trigger_system_agent")
    @patch("issuelab.observer_trigger.is_system_agent")
    def test_auto_trigger_returns_false_on_failure(self, mock_is_system, mock_trigger_system):
        """触发失败应该返回False"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_system.return_value = True
        mock_trigger_system.return_value = False

        result = auto_trigger_agent(agent_name="observer", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False


class TestObserveBatchIntegration:
    """测试observe-batch命令的自动触发功能"""

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_triggers_on_should_trigger_true(self, mock_auto_trigger):
        """observe-batch结果为should_trigger=True时应该自动触发"""
        from issuelab.observer_trigger import process_observer_results

        mock_auto_trigger.return_value = True

        results = [
            {
                "issue_number": 1,
                "should_trigger": True,
                "agent": "moderator",
                "reason": "New paper needs review",
            }
        ]

        issue_data = {1: {"title": "Test", "body": "Body"}}

        triggered = process_observer_results(results, issue_data, auto_trigger=True)

        assert triggered == 1
        mock_auto_trigger.assert_called_once()

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_skips_when_should_trigger_false(self, mock_auto_trigger):
        """observe-batch结果为should_trigger=False时不应该触发"""
        from issuelab.observer_trigger import process_observer_results

        results = [{"issue_number": 1, "should_trigger": False, "reason": "Not ready"}]

        issue_data = {1: {"title": "Test", "body": "Body"}}

        triggered = process_observer_results(results, issue_data, auto_trigger=True)

        assert triggered == 0
        mock_auto_trigger.assert_not_called()

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_handles_multiple_issues(self, mock_auto_trigger):
        """observe-batch应该能处理多个issues的触发"""
        from issuelab.observer_trigger import process_observer_results

        mock_auto_trigger.return_value = True

        results = [
            {"issue_number": 1, "should_trigger": True, "agent": "moderator", "reason": "Reason 1"},
            {"issue_number": 2, "should_trigger": False, "reason": "Not ready"},
            {"issue_number": 3, "should_trigger": True, "agent": "gqy22", "reason": "Reason 3"},
        ]

        issue_data = {1: {"title": "Test1", "body": "Body1"}, 3: {"title": "Test3", "body": "Body3"}}

        triggered = process_observer_results(results, issue_data, auto_trigger=True)

        assert triggered == 2
        assert mock_auto_trigger.call_count == 2
