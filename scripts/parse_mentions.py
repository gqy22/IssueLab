#!/usr/bin/env python3
"""
GitHub Actions wrapper for mention parsing.

Lightweight wrapper that calls the core logic from issuelab.cli.mentions.
This allows fast startup in CI/CD without installing the full package.
"""

import sys
from pathlib import Path

# Add src to path for direct script execution
if __name__ == "__main__":
    src_path = Path(__file__).parent.parent / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

    from issuelab.cli.mentions import main

    sys.exit(main())
