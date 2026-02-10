"""Helpers for extracting YAML content from model responses."""

import re


def extract_yaml_block(text: str) -> str:
    """Extract the first fenced ```yaml block, or return empty string."""
    match = re.search(r"```yaml(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""
