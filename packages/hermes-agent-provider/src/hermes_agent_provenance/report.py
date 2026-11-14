"""List Hermes sessions that were shown a source which has been withdrawn since.

Usage: hermes-provenance-exposure [--home HERMES_HOME]
Exit code 0 when no session is exposed, 1 when at least one is, 2 on error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-provenance-exposure")
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    args = parser.parse_args(argv)
    from . import PROVIDER_NAME, load_config
    from .store import Store

    root = Path(args.home) / PROVIDER_NAME
    if not (root / "authority" / "authority.db").exists():
        print(json.dumps({"error": f"no provenance store under {root}"}))
        return 2
    report = Store(root, str(load_config(args.home)["workspace"])).exposure_report()
    print(json.dumps({"exposed_sessions": report}, indent=2, ensure_ascii=False))
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
