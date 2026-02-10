#!/usr/bin/env python3
"""
Prepare MCP environment variables from .mcp.json placeholder references.

Usage examples:
  python scripts/prepare_mcp_env.py --agent gqy20 --write-github-env
  python scripts/prepare_mcp_env.py --agent gqy20 --shell
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
SAFE_ENV_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _walk_for_placeholders(value: Any, bucket: set[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _walk_for_placeholders(v, bucket)
        return
    if isinstance(value, list):
        for v in value:
            _walk_for_placeholders(v, bucket)
        return
    if isinstance(value, str):
        for match in ENV_VAR_PATTERN.findall(value):
            bucket.add(match)


def _read_mcp_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read {path}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(raw, dict):
        return {}
    servers = raw.get("mcpServers", raw)
    return servers if isinstance(servers, dict) else {}


def _collect_required_env_names(paths: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in paths:
        servers = _read_mcp_file(path)
        _walk_for_placeholders(servers, names)
    return names


def _parse_env_json(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[WARN] ISSUELAB_MCP_ENV_JSON is invalid JSON: {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print("[WARN] ISSUELAB_MCP_ENV_JSON must be a JSON object", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        if not SAFE_ENV_KEY.match(k):
            continue
        out[k] = "" if v is None else str(v)
    return out


def _resolve_env_values(required: set[str], extra_map: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in sorted(required):
        value = os.environ.get(name)
        if value is None or value == "":
            value = extra_map.get(name, "")
        if value == "":
            missing.append(name)
            continue
        resolved[name] = value
    return resolved, missing


def _escape_shell(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve MCP env placeholders for an agent")
    parser.add_argument("--root-dir", default=".", help="Project root directory")
    parser.add_argument("--agent", help="Agent name to include agents/<agent>/.mcp.json")
    parser.add_argument(
        "--all-agents",
        action="store_true",
        help="Include all agents/*/.mcp.json files",
    )
    parser.add_argument(
        "--include-root-mcp",
        action="store_true",
        help="Include root .mcp.json",
    )
    parser.add_argument(
        "--write-github-env",
        action="store_true",
        help="Append resolved env vars to $GITHUB_ENV",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print shell export commands to stdout",
    )
    args = parser.parse_args(argv)

    root = Path(args.root_dir).resolve()
    mcp_paths: list[Path] = []
    if args.include_root_mcp:
        mcp_paths.append(root / ".mcp.json")
    if args.agent:
        mcp_paths.append(root / "agents" / args.agent / ".mcp.json")
    if args.all_agents:
        for path in sorted((root / "agents").glob("*/.mcp.json")):
            mcp_paths.append(path)

    required = _collect_required_env_names(mcp_paths)
    extra_map = _parse_env_json(os.environ.get("ISSUELAB_MCP_ENV_JSON", ""))
    resolved, missing = _resolve_env_values(required, extra_map)

    if args.write_github_env:
        github_env = os.environ.get("GITHUB_ENV")
        if not github_env:
            print("[WARN] GITHUB_ENV not set, skip write-github-env", file=sys.stderr)
        else:
            with open(github_env, "a", encoding="utf-8") as fh:
                for key, value in resolved.items():
                    fh.write(f"{key}<<__MCP_ENV_EOF__\n{value}\n__MCP_ENV_EOF__\n")

    if args.shell:
        for key, value in resolved.items():
            print(f'export {key}="{_escape_shell(value)}"')

    print(f"Resolved MCP env vars: {len(resolved)}", file=sys.stderr)
    if missing:
        print(f"Missing MCP env vars: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
