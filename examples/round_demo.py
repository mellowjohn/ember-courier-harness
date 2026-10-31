"""Run one complete audit-backed round with two clean verification checkouts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.staged_fix_demo import main

if __name__ == "__main__":
    result = main(with_rounds=True)
    print("Audit-backed round report: " + result["round_report"]["path"])
