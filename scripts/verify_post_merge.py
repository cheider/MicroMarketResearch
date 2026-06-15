"""
Post-merge verification: pytest + diff of API-critical paths vs main backup.

Usage:
    python scripts/verify_post_merge.py
    python scripts/verify_post_merge.py --main-dir "../backup_of_micromarket/MicroMarketResearch"
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAIN = ROOT.parent / "backup_of_micromarket" / "MicroMarketResearch"

API_PATHS = [
    "app/clover/client.py",
    "app/config.py",
    "app/etl/ingest.py",
    "app/etl/transform.py",
    "app/etl/load.py",
    "app/routes/ingest.py",
    "scripts/seed_sandbox.py",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-dir",
        type=Path,
        default=DEFAULT_MAIN,
        help="Path to main-branch MicroMarketResearch clone",
    )
    args = parser.parse_args()
    main_dir = args.main_dir

    print("Post-merge verification")
    print("=" * 60)

    if main_dir.is_dir():
        print(f"Main reference: {main_dir}")
        for rel in API_PATHS:
            cur = ROOT / rel
            ref = main_dir / rel
            if not ref.exists():
                print(f"  [skip] {rel} (not on main)")
                continue
            if not cur.exists():
                print(f"  [NEW]  {rel}")
                continue
            if cur.read_text(encoding="utf-8", errors="replace") == ref.read_text(
                encoding="utf-8", errors="replace"
            ):
                print(f"  [OK]   {rel} matches main")
            else:
                print(f"  [DIFF] {rel} differs from main — review for API impact")
    else:
        print(f"Main dir not found: {main_dir}")
        print("  Skipping file compare; run pytest only.")

    print("-" * 60)
    print("Running pytest -q ...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(ROOT),
        env=env,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
