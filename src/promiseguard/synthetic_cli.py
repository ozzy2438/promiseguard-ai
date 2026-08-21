"""CLI entry point for reproducible synthetic-data generation."""

from __future__ import annotations

import argparse

from promiseguard.synthetic import SyntheticDataGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--output", default="data/generated/orders.jsonl")
    args = parser.parse_args()
    destination = SyntheticDataGenerator(seed=args.seed).write_jsonl(args.output, count=args.count)
    print(destination)


if __name__ == "__main__":
    main()
