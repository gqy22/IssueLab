"""Tests for CLI tools."""

import json
import tempfile
from pathlib import Path

import pytest

from issuelab.cli.mentions import parse_github_mentions


class TestParseMentions:
    """Tests for mention parsing."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("@alice please review", ["alice"]),
            ("@alice @bob @charlie", ["alice", "bob", "charlie"]),
            ("@alice @bob @alice @charlie @bob", ["alice", "bob", "charlie"]),
            ("@user-name @test-user-123", ["user-name", "test-user-123"]),
            # 正则会匹配 @-invalid 的 invalid 和 @123 的 123；与 GitHub 实际行为一致
            ("@-invalid @invalid- @123", ["invalid", "123"]),
            ("This is a normal text without any mentions", []),
        ],
    )
    def test_parse_mentions_basic_cases(self, text: str, expected: list[str]):
        """基础 mention 提取场景。"""
        assert parse_github_mentions(text) == expected

    def test_empty_text(self):
        """Test empty input."""
        assert parse_github_mentions("") == []
        assert parse_github_mentions(None) == []

    def test_mention_in_markdown(self):
        """Test mentions in markdown context."""
        text = """
        # Issue Title

        @alice can you review this?

        ```python
        # This @bob is in code, but will be matched
        print("test")
        ```

        cc @charlie
        """
        mentions = parse_github_mentions(text)
        assert "alice" in mentions
        assert "bob" in mentions
        assert "charlie" in mentions

    def test_controlled_section_only(self):
        """Only parse mentions inside controlled sections."""
        text = """
        普通正文 @noise
        ---
        相关人员: @alice @bob
        """
        mentions = parse_github_mentions(text, controlled_section_only=True)
        assert mentions == ["alice", "bob"]

    def test_controlled_section_list_format(self):
        """Parse list format under 协作请求."""
        text = """
        协作请求:
        - @alice
        - @bob
        """
        mentions = parse_github_mentions(text, controlled_section_only=True)
        assert mentions == ["alice", "bob"]

    def test_controlled_section_only_reads_trailing_block(self):
        """Ignore historical mentions in body, read only trailing controlled block."""
        text = """
        历史记录：
        相关人员: @old_agent

        正文继续...

        ---
        相关人员: @alice @bob
        """
        mentions = parse_github_mentions(text, controlled_section_only=True)
        assert mentions == ["alice", "bob"]


class TestMentionsCLI:
    """Tests for mentions CLI."""

    def test_cli_csv_output(self, capsys):
        """Test CSV output format (default)."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob"])
        assert result == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == "alice,bob"

    def test_cli_json_output(self, capsys):
        """Test JSON output format."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob", "--output", "json"])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["mentions"] == ["alice", "bob"]
        assert output["count"] == 2

    def test_cli_text_output(self, capsys):
        """Test text output format."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob", "--output", "text"])
        assert result == 0

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines == ["alice", "bob"]

    def test_cli_no_input(self, capsys):
        """Test error on no input."""
        from issuelab.cli.mentions import main

        result = main([])
        assert result == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_cli_controlled_section_only(self, capsys):
        """CLI controlled-section mode ignores free-text mentions."""
        from issuelab.cli.mentions import main

        body = "正文 @noise\n---\n相关人员: @alice @bob"
        result = main(["--issue-body", body, "--controlled-section-only"])
        assert result == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == "alice,bob"


class TestParseAgentsArg:
    """Tests for parse_agents_arg function."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("moderator,reviewer_a,observer", ["moderator", "reviewer_a", "observer"]),
            ("moderator reviewer_a observer", ["moderator", "reviewer_a", "observer"]),
            ('["moderator", "reviewer_a"]', ["moderator", "reviewer_a"]),
            ("Moderator,REVIEWER_A,Observer", ["moderator", "reviewer_a", "observer"]),
            ("  moderator , reviewer_a , observer  ", ["moderator", "reviewer_a", "observer"]),
        ],
    )
    def test_parse_agents_arg_variants(self, raw: str, expected: list[str]):
        """支持 CSV/空格/JSON 与大小写、空白处理。"""
        from issuelab.__main__ import parse_agents_arg

        assert parse_agents_arg(raw) == expected


class TestDispatch:
    """Tests for dispatch functionality."""

    def test_load_empty_registry(self):
        """Test loading from non-existent directory."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "non_existent"
            registry = load_registry(non_existent)
            assert registry == {}

    def test_load_valid_registry(self):
        """Test loading valid registry files."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)

            # Create test agent directory with agent.yml
            alice_dir = agents_dir / "alice"
            alice_dir.mkdir()
            config_file = alice_dir / "agent.yml"
            config_file.write_text("""
owner: alice
repository: alice/IssueLab
triggers:
  - "@alice"
enabled: true
""")

            registry = load_registry(agents_dir)
            assert "alice" in registry
            assert registry["alice"]["owner"] == "alice"
            assert registry["alice"]["repository"] == "alice/IssueLab"

    def test_load_disabled_agent(self):
        """Test that disabled agents are not loaded."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)

            # Create test agent directory with agent.yml
            bob_dir = agents_dir / "bob"
            bob_dir.mkdir()
            config_file = bob_dir / "agent.yml"
            config_file.write_text("""
owner: bob
repository: bob/IssueLab
triggers:
  - "@bob"
enabled: false
""")

            registry = load_registry(agents_dir)
            assert "bob" not in registry

    def test_match_triggers(self):
        """Test trigger matching."""
        from issuelab.cli.dispatch import match_triggers

        registry = {
            "alice": {"owner": "alice", "repository": "alice/IssueLab", "triggers": ["@alice"]},
            "bob": {"owner": "bob", "repository": "bob/IssueLab", "triggers": ["@bob", "@bob-cv"]},
            "carol": {"owner": "carol", "repository": "carol/IssueLab"},
        }

        # Test direct match
        matched = match_triggers(["alice"], registry)
        assert len(matched) == 1
        assert matched[0]["owner"] == "alice"

        # Test multiple matches
        matched = match_triggers(["alice", "bob"], registry)
        assert len(matched) == 2

        # Test no match
        matched = match_triggers(["charlie"], registry)
        assert len(matched) == 0

        # Test default match
        matched = match_triggers(["carol"], registry)
        assert len(matched) == 1
        assert matched[0]["owner"] == "carol"

    def test_dispatch_mentions_skips_system_agents(self, monkeypatch):
        """System agents should be ignored by dispatch workflow."""
        from issuelab.cli.dispatch import dispatch_mentions

        monkeypatch.setattr(
            "issuelab.cli.dispatch.load_registry",
            lambda _agents_dir: {
                "moderator": {
                    "owner": "moderator",
                    "repository": "gqy20/IssueLab",
                    "agent_type": "system",
                },
                "alice": {
                    "owner": "alice",
                    "repository": "gqy20/IssueLab",
                    "agent_type": "user",
                },
            },
        )

        summary = dispatch_mentions(
            mentions=["moderator", "alice"],
            agents_dir="agents",
            source_repo="gqy20/IssueLab",
            issue_number=1,
            dry_run=True,
            app_id="fake_app_id",
            app_private_key="fake_private_key",
        )

        assert summary["total_count"] == 1
        assert summary["success_count"] == 1
        assert summary["local_agents"] == ["alice"]


class TestDispatchCLI:
    """Tests for dispatch CLI mention parsing."""

    @pytest.mark.parametrize("mentions", ['["alice", "bob"]', "alice,bob"])
    def test_parse_mentions_inputs(self, monkeypatch, mentions: str):
        """支持 JSON 与 CSV mentions 输入格式。"""
        from issuelab.cli.dispatch import main

        # Mock environment
        monkeypatch.setenv("GITHUB_APP_ID", "fake_app_id")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake_private_key")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty agents directory
            agents_dir = Path(tmpdir)
            agents_dir.mkdir(exist_ok=True)

            # Should handle JSON format
            result = main(
                [
                    "--mentions",
                    mentions,
                    "--agents-dir",
                    str(agents_dir),
                    "--source-repo",
                    "test/repo",
                    "--issue-number",
                    "1",
                ]
            )

            # Returns 0 even with no matches (no agents to dispatch to)
            assert result == 0
