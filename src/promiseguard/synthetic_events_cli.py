"""CLI for generating anomaly-labelled operational event streams."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

from promiseguard.models import SyntheticRecord
from promiseguard.synthetic_events import SyntheticEventStreamGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/generated/orders.jsonl")
    parser.add_argument("--output", default="data/generated/events.jsonl")
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--duplicate-rate", type=float, default=0.01)
    parser.add_argument("--late-arrival-rate", type=float, default=0.02)
    parser.add_argument("--out-of-order-rate", type=float, default=0.02)
    args = parser.parse_args()

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    generator = SyntheticEventStreamGenerator(seed=args.seed)
    with destination.open("w", encoding="utf-8") as handle:
        for envelope in generator.generate(
            _records(Path(args.input)),
            duplicate_rate=args.duplicate_rate,
            late_arrival_rate=args.late_arrival_rate,
            out_of_order_rate=args.out_of_order_rate,
        ):
            handle.write(envelope.model_dump_json())
            handle.write("\n")
    print(destination)


def _records(path: Path) -> Iterator[SyntheticRecord]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            yield SyntheticRecord.model_validate(json.loads(line))


if __name__ == "__main__":
    main()
