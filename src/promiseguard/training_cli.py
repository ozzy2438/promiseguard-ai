"""CLI entry point for training calibrated promise-risk models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from promiseguard.models import SyntheticRecord
from promiseguard.training import train_risk_models


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/generated/orders.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models")
    parser.add_argument("--no-lightgbm", action="store_true")
    args = parser.parse_args()

    records: list[SyntheticRecord] = []
    with Path(args.input).open(encoding="utf-8") as handle:
        for line in handle:
            records.append(SyntheticRecord.model_validate(json.loads(line)))
    summary = train_risk_models(
        records,
        output_dir=args.output_dir,
        include_lightgbm=not args.no_lightgbm,
    )
    print(summary.metrics_path)


if __name__ == "__main__":
    main()
