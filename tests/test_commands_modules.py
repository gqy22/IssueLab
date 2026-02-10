"""Tests for split command modules."""

from argparse import Namespace


def test_common_run_agents_command_passes_trigger_comment(monkeypatch):
    from issuelab.commands import common

    captured = {}

    async def fake_run_agents_parallel(
        issue, agents, context, comment_count, available_agents=None, trigger_comment=None
    ):
        captured["trigger_comment"] = trigger_comment
        return {}

    monkeypatch.setenv("ISSUELAB_TRIGGER_COMMENT", "@x ping")
    monkeypatch.setattr(common, "run_agents_parallel", fake_run_agents_parallel)

    common.run_agents_command(1, ["moderator"], "ctx", 0)
    assert captured["trigger_comment"] == "@x ping"


def test_common_maybe_post_agent_result_returns_false_on_post_failure(monkeypatch):
    from issuelab.commands.common import maybe_post_agent_result

    monkeypatch.setattr("issuelab.commands.common.post_comment", lambda *a, **k: False)
    result = maybe_post_agent_result(1, "moderator", "ok", {"ok": True, "response": "hello"})
    assert result is False


def test_core_handle_execute_returns_error_for_empty_agents():
    from issuelab.commands.core import handle_execute

    args = Namespace(issue=1, agents="", post=False)
    ret = handle_execute(args, "ctx", 0, lambda _: [])
    assert ret == 1


def test_core_handle_execute_calls_runner(monkeypatch):
    from issuelab.commands import core

    args = Namespace(issue=1, agents="moderator", post=False)
    called = {}

    def fake_runner(issue, agents, context, comment_count, *, post=False, repo=None, available_agents=None):
        called["issue"] = issue
        called["agents"] = agents
        called["post"] = post
        return {}

    monkeypatch.setattr(core, "run_agents_command", fake_runner)
    ret = core.handle_execute(args, "ctx", 3, lambda _: ["moderator"])

    assert ret is None
    assert called == {"issue": 1, "agents": ["moderator"], "post": False}


def test_personal_reply_minimal_path_without_config_parse(monkeypatch):
    from issuelab.commands import personal

    args = Namespace(
        agent="gqy22",
        issue=7,
        repo="owner/repo",
        issue_title="T",
        issue_body="B",
        available_agents="",
        post=False,
    )

    calls = {"safe_load": 0, "run": 0}

    def fake_safe_load(_stream):
        calls["safe_load"] += 1
        return {"ignored": True}

    def fake_run_agents_command(issue, agents, context, comment_count, *, post=False, repo=None, available_agents=None):
        calls["run"] += 1
        return {"gqy22": {"response": "ok", "ok": True}}

    monkeypatch.setattr("yaml.safe_load", fake_safe_load)
    monkeypatch.setattr(personal, "run_agents_command", fake_run_agents_command)

    ret = personal.handle_personal_reply(args)
    assert ret is None
    # personal-reply should not parse agent.yml content.
    assert calls["safe_load"] == 0
    assert calls["run"] == 1
