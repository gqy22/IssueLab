"""Tests for YAML text parsing helpers."""

from issuelab.utils.yaml_text import extract_yaml_block


def test_extract_yaml_block_from_fenced_markdown():
    text = """Some text

```yaml
summary: "ok"
findings:
  - "a"
```
"""
    assert extract_yaml_block(text) == 'summary: "ok"\nfindings:\n  - "a"'


def test_extract_yaml_block_returns_empty_when_missing():
    assert extract_yaml_block("no fenced yaml here") == ""
