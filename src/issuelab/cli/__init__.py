"""CLI tools for IssueLab."""

from .mentions import main as parse_mentions_main
from .mentions import parse_github_mentions

# 向后兼容接口
parse_mentions = parse_github_mentions

__all__ = [
    "parse_github_mentions",
    "parse_mentions",  # 向后兼容
    "parse_mentions_main",
]


# Lazy import to avoid heavy dependencies
def dispatch_main():
    """Lazy import for dispatch main."""
    from .dispatch import main

    return main


def dispatch_to_users(*args, **kwargs):
    """Lazy import for dispatch_to_users."""
    from .dispatch import dispatch_event

    return dispatch_event(*args, **kwargs)
