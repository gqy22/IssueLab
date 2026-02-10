"""Shared mention parsing helpers."""

import re

# GitHub username pattern: alnum/underscore, can include internal hyphen/underscore.
GITHUB_MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_](?:[a-zA-Z0-9_-]*[a-zA-Z0-9_])?)")


def extract_github_mentions(text: str | None) -> list[str]:
    """Extract deduplicated @mentions while preserving order."""
    if not text:
        return []

    matches = GITHUB_MENTION_PATTERN.findall(text)

    seen: set[str] = set()
    result: list[str] = []
    for username in matches:
        if username not in seen:
            seen.add(username)
            result.append(username)
    return result


def extract_controlled_mentions(text: str | None) -> list[str]:
    """Extract mentions only from the trailing controlled collaboration section."""
    if not text:
        return []

    lines = text.splitlines()
    if not lines:
        return []

    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    if end < 0:
        return []

    result: list[str] = []
    seen: set[str] = set()

    # Case 1: 文末为单行 "相关人员: @a @b"
    tail = lines[end].strip()
    if "相关人员:" in tail:
        suffix = tail.split("相关人员:", 1)[1]
        for username in extract_github_mentions(suffix):
            if username not in seen:
                seen.add(username)
                result.append(username)
        return result

    # Case 2: 文末为列表形式
    list_lines: list[str] = []
    idx = end
    while idx >= 0 and re.match(r"^\s*-\s+@", lines[idx]):
        list_lines.append(lines[idx])
        idx -= 1

    if list_lines and idx >= 0 and lines[idx].strip().startswith("协作请求:"):
        for line in reversed(list_lines):
            for username in extract_github_mentions(line):
                if username not in seen:
                    seen.add(username)
                    result.append(username)
    return result
