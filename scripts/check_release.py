"""Fail the build if the combined frontend artifact is incomplete."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.release import DIST, validate_website


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DIST)
    parser.add_argument("--write-metadata", action="store_true")
    args = parser.parse_args()
    try:
        assets = validate_website(args.dist)
        commit = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GITHUB_SHA")
        if not commit:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True
                )
                commit = result.stdout.strip()
            except FileNotFoundError:
                commit = None
        if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
            commit = None
        if args.write_metadata:
            (args.dist / "release.json").write_text(
                json.dumps({"commit": commit}) + "\n", encoding="utf-8"
            )
        print(json.dumps({"status": "ready", "assets": len(assets), "commit": commit}))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
