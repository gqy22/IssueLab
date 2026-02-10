"""测试代理模块"""

from pathlib import Path

import yaml

from issuelab.agents import (
    discover_agents,
    get_available_agents,
    load_prompt,
    normalize_agent_name,
)


def test_normalize_agent_name():
    """normalize_agent_name 应该返回标准化名称"""
    assert normalize_agent_name("MODERATOR") == "moderator"
    assert normalize_agent_name("reviewer_a") == "reviewer_a"
    assert normalize_agent_name("reviewer_b") == "reviewer_b"
    assert normalize_agent_name("summarizer") == "summarizer"
    # 测试不存在的名称
    assert normalize_agent_name("unknown") == "unknown"
    assert normalize_agent_name("mod") == "mod"


def test_discover_agents():
    """测试动态发现功能"""
    agents = discover_agents()

    assert isinstance(agents, dict)
    assert len(agents) >= 4

    # 验证必需的 agent 都存在
    required_agents = ["moderator", "reviewer_a", "reviewer_b", "summarizer"]
    for agent in required_agents:
        assert agent in agents, f"Agent {agent} not found"
        assert "description" in agents[agent]
        assert "prompt" in agents[agent]
        assert len(agents[agent]["prompt"]) > 0


def test_agent_metadata_parsing():
    """测试 YAML 元数据解析"""
    agents = discover_agents()

    # 验证 observer 存在且触发条件为空列表或 None
    if "observer" in agents:
        trigger = agents["observer"]["trigger_conditions"]
        assert trigger == [] or trigger is None or trigger == "", "Observer should have empty trigger conditions"

    # 验证 moderator 有正确的元数据
    assert "moderator" in agents
    assert "审核" in agents["moderator"]["description"] or "调度" in agents["moderator"]["description"]


def test_load_prompt_returns_string():
    """load_prompt 应该返回字符串（纯提示词正文）"""
    result = load_prompt("moderator")
    assert isinstance(result, str)
    assert len(result) > 0
    # 验证 prompt 文件使用纯 markdown 正文
    assert not result.startswith("---")


def test_load_prompt_unknown_agent():
    """load_prompt 对未知代理返回空字符串"""
    result = load_prompt("unknown_agent_xyz_123")
    assert result == ""


def test_get_available_agents():
    """get_available_agents 应该返回所有可用代理"""
    agents = get_available_agents()
    assert "moderator" in agents
    assert "reviewer_a" in agents
    assert "reviewer_b" in agents
    assert "summarizer" in agents
    assert "observer" in agents
    assert "video_manim" in agents
    assert len(agents) >= 5


class TestDiscoverAgentsCache:
    """测试 discover_agents 的缓存行为"""

    def test_discover_agents_cache_reuse_and_invalidate(self, tmp_path, monkeypatch):
        from issuelab.agents import discovery as discovery_mod

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "moderator").mkdir()
        (agents_dir / "moderator" / "agent.yml").write_text(
            "name: moderator\nowner: moderator\ndescription: test\nrepository: gqy20/IssueLab\n",
            encoding="utf-8",
        )

        prompt_path = agents_dir / "moderator" / "prompt.md"
        prompt_path.write_text(
            "---\nagent: moderator\ndescription: test\n---\n# Moderator\nv1",
            encoding="utf-8",
        )

        monkeypatch.setattr(discovery_mod, "AGENTS_DIR", agents_dir)

        agents_v1 = discovery_mod.discover_agents()
        agents_v1_again = discovery_mod.discover_agents()

        assert agents_v1 is agents_v1_again
        assert "moderator" in agents_v1
        assert "v1" in agents_v1["moderator"]["prompt"]

        prompt_path.write_text(
            "---\nagent: moderator\ndescription: test\n---\n# Moderator\nv2",
            encoding="utf-8",
        )
        # 确保 mtime 变化（避免文件系统时间粒度导致缓存未失效）
        import os

        new_mtime = prompt_path.stat().st_mtime + 2
        os.utime(prompt_path, (new_mtime, new_mtime))

        agents_v2 = discovery_mod.discover_agents()
        assert agents_v2 is not agents_v1
        assert "v2" in agents_v2["moderator"]["prompt"]


def test_system_prompt_loaded_from_agents_dir(tmp_path, monkeypatch):
    """系统 agent 应从 agents/<name>/prompt.md 读取。"""
    from issuelab.agents import discovery as discovery_mod

    agents_dir = tmp_path / "agents"
    (agents_dir / "moderator").mkdir(parents=True)

    (agents_dir / "moderator" / "agent.yml").write_text(
        "name: moderator\nowner: moderator\ndescription: from-agent-yml\nrepository: gqy20/IssueLab\n",
        encoding="utf-8",
    )
    (agents_dir / "moderator" / "prompt.md").write_text(
        "# Moderator\nfrom agents",
        encoding="utf-8",
    )

    monkeypatch.setattr(discovery_mod, "AGENTS_DIR", agents_dir)
    discovery_mod._CACHED_AGENTS = None
    discovery_mod._CACHED_SIGNATURE = None

    agents = discovery_mod.discover_agents()
    assert "moderator" in agents
    assert "from agents" in agents["moderator"]["prompt"]
    assert agents["moderator"]["description"] == "from-agent-yml"


def test_system_agents_have_output_template():
    """所有 system agent 必须配置 output_template，且模板必须可解析。"""
    templates_file = Path("config/output_templates.yml")
    templates_doc = yaml.safe_load(templates_file.read_text(encoding="utf-8")) or {}
    global_templates = templates_doc.get("templates", {}) if isinstance(templates_doc, dict) else {}

    for agent_yml in Path("agents").glob("*/agent.yml"):
        config = yaml.safe_load(agent_yml.read_text(encoding="utf-8")) or {}
        if config.get("agent_type") != "system":
            continue

        output_template = config.get("output_template")
        assert isinstance(output_template, str) and output_template.strip(), f"{agent_yml} missing output_template"

        if output_template.startswith("local:"):
            local_name = output_template.split(":", 1)[1].strip()
            local_file = agent_yml.parent / "output_config.yml"
            local_doc = yaml.safe_load(local_file.read_text(encoding="utf-8")) if local_file.exists() else {}
            local_templates = local_doc.get("templates", {}) if isinstance(local_doc, dict) else {}
            assert local_name in local_templates, f"{agent_yml} references missing local template {local_name}"
        else:
            assert (
                output_template in global_templates
            ), f"{agent_yml} references missing global template {output_template}"
