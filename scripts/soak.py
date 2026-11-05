"""Run campaigns of faults on four real processes, one after the other, for as long as asked.

    python scripts/soak.py --minutes 60 --seed 1 --out soak.jsonl

Each campaign starts a new deployment, so nothing carries over from one to the next. One JSON line
per campaign goes to `--out`, and the exit code is 1 if any campaign found a problem. What it shows is
in tests/chaos.py. A long run on one machine is not a substitute for weeks on separate ones.
"""

import argparse
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.chaos import Campaign, ChaosDeployment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--campaign-seconds", type=float, default=120.0)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()

    deadline = time.monotonic() + options.minutes * 60
    seed = options.seed
    failures = 0

    with options.out.open("a") as out:
        while time.monotonic() < deadline:
            with tempfile.TemporaryDirectory() as directory:
                deployment = ChaosDeployment(
                    Path(directory),
                    random.Random(seed),
                    extra_senders=1,
                    balance=1_000_000,
                )
                deployment.start_all()
                change = Campaign.change_committee if seed % 2 else None

                try:
                    report = Campaign(deployment, seed, epoch_change=change).run(
                        seconds=options.campaign_seconds
                    )
                finally:
                    deployment.close()

            print(report.to_json(), file=out, flush=True)
            failures += not report.safe
            seed += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
