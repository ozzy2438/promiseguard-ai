"""CLI for synthetic counterfactual business-value evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

from promiseguard.models import SyntheticRecord
from promiseguard.trained_risk import TrainedRiskScorer
from promiseguard.value_evaluation import SyntheticValueEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/generated/orders.jsonl")
    parser.add_argument("--output", default="artifacts/evidence/value_evaluation.json")
    parser.add_argument("--model-path")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    scorer = TrainedRiskScorer(args.model_path) if args.model_path else None
    evaluator = SyntheticValueEvaluator(scorer=scorer)
    records = _records(Path(args.input), limit=args.limit)
    summary = evaluator.evaluate(records)

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary.to_json_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(destination)


def _records(path: Path, *, limit: int | None) -> Iterator[SyntheticRecord]:
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit is not None and index >= limit:
                break
            yield SyntheticRecord.model_validate(json.loads(line))


if __name__ == "__main__":
    main()
