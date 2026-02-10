"""Agent registry and rules (single source of truth).

This module centralizes agent registry loading from `agents/<name>/agent.yml`
and derives behavior from configuration instead of hardcoded name lists.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

AGENT_TYPE_SYSTEM = "system"
AGENT_TYPE_USER = "user"


def normalize_agent_name(name: str) -> str:
    """Normalize agent name by registry key (case-insensitive)."""
    if not name:
        return name
    config = get_agent_config(name, include_disabled=True)
    if not config:
        return name
    canonical = config.get("owner") or config.get("username")
    if isinstance(canonical, str) and canonical:
        return canonical
    return name


def _normalize_agent_type(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {AGENT_TYPE_SYSTEM, AGENT_TYPE_USER}:
            return cleaned
    return None


def load_registry(agents_dir: Path, include_disabled: bool = False) -> dict[str, dict[str, Any]]:
    """
    Load agent registry from agents/<user>/agent.yml.

    Args:
        agents_dir: agents directory path
        include_disabled: whether to include disabled agents

    Returns:
        username -> config dict
    """
    registry: dict[str, dict[str, Any]] = {}

    if not agents_dir.exists():
        logger.warning("Agents directory not found: %s", agents_dir)
        return registry

    for user_dir in agents_dir.iterdir():
        if not user_dir.is_dir():
            continue
        if user_dir.name.startswith("_"):
            continue

        agent_yml = user_dir / "agent.yml"
        if not agent_yml.exists():
            continue

        try:
            with open(agent_yml, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning("Empty config in %s", agent_yml)
                continue

            # Use owner or username as key
            username = config.get("owner") or config.get("username")
            if not username:
                logger.warning("%s missing 'owner' or 'username'", agent_yml)
                continue

            # Skip disabled unless requested
            if not include_disabled and not config.get("enabled", True):
                logger.info("%s is disabled, skipping", username)
                continue

            registry[username] = config

        except yaml.YAMLError as e:
            logger.error("Error parsing %s: %s", agent_yml.name, e)
        except Exception as e:
            logger.error("Error loading %s: %s", agent_yml.name, e)

    return registry


def get_agent_config(
    agent_name: str, agents_dir: Path | None = None, include_disabled: bool = False
) -> dict[str, Any] | None:
    """Get a single agent config by name."""
    if not agent_name:
        return None
    root = agents_dir or Path("agents")
    registry = load_registry(root, include_disabled=include_disabled)
    normalized = agent_name.lower()
    for name, config in registry.items():
        if str(name).lower() == normalized:
            return config
    return None


def is_system_agent(
    agent_name: str, agents_dir: Path | None = None, include_disabled: bool = True
) -> tuple[bool, dict[str, Any] | None]:
    """Determine whether an agent is a system agent.

    Source of truth: agent.yml field `agent_type: system|user`.
    If `agent_type` is absent or invalid, it is treated as non-system.
    """
    config = get_agent_config(agent_name, agents_dir=agents_dir, include_disabled=include_disabled)
    if not config:
        return False, None
    parsed = _normalize_agent_type(config.get("agent_type"))
    return parsed == AGENT_TYPE_SYSTEM, config


def is_registered_agent(
    agent_name: str, agents_dir: Path | None = None, include_disabled: bool = False
) -> tuple[bool, dict[str, Any] | None]:
    """Check if an agent is registered."""
    config = get_agent_config(agent_name, agents_dir=agents_dir, include_disabled=include_disabled)
    return (config is not None), config
