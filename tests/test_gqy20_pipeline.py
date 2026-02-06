import pytest


def test_gqy20_multistage_toggle(monkeypatch):
    from issuelab.agents.executor import _is_gqy20_multistage_enabled

    monkeypatch.delenv("ISSUELAB_GQY20_MULTISTAGE", raising=False)
    assert _is_gqy20_multistage_enabled("gqy20") is True
    assert _is_gqy20_multistage_enabled("moderator") is False

    monkeypatch.setenv("ISSUELAB_GQY20_MULTISTAGE", "0")
    assert _is_gqy20_multistage_enabled("gqy20") is False


def test_collect_source_urls_prefers_yaml_sources():
    from issuelab.agents.executor import _collect_source_urls

    text = """```yaml
summary: "s"
findings: []
recommendations: []
sources:
  - "https://example.com/1"
  - "https://example.com/2"
confidence: "high"
```
Other link: https://ignored.example.com/x
"""
    urls = _collect_source_urls(text)
    assert urls == ["https://example.com/1", "https://example.com/2"]


@pytest.mark.asyncio
async def test_gqy20_multistage_judge_retry_then_success(monkeypatch):
    from issuelab.agents import executor as ex

    calls = {"count": 0}

    async def fake_run_single_agent(prompt: str, agent_name: str):
        calls["count"] += 1
        stage = calls["count"]
        if stage <= 4:
            response = """```yaml
summary: "ok"
findings: []
recommendations: []
confidence: "medium"
```"""
        elif stage == 5:
            # First Judge: no sources, should trigger retry
            response = """```yaml
summary: "judge"
findings:
  - "f"
recommendations:
  - "r"
sources: []
confidence: "medium"
```"""
        else:
            response = """```yaml
summary: "judge"
findings:
  - "f"
recommendations:
  - "r"
sources:
  - "https://example.com/final"
confidence: "high"
```"""

        return {
            "response": response,
            "cost_usd": 0.01,
            "num_turns": 1,
            "tool_calls": ["Read"],
            "input_tokens": 10,
            "output_tokens": 10,
            "total_tokens": 20,
        }

    monkeypatch.setattr(ex, "run_single_agent", fake_run_single_agent)

    result = await ex._run_gqy20_multistage("base prompt", 1, "ctx")
    assert "https://example.com/final" in result["response"]
    assert calls["count"] >= 6
    assert result["cost_usd"] > 0
