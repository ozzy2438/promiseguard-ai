"""Run the smallest deterministic PromiseGuard shadow decision."""

from __future__ import annotations

import json

from promiseguard.models import OperatingMode
from promiseguard.orchestrator import PromiseGuardOrchestrator
from promiseguard.synthetic import SyntheticDataGenerator


def main() -> None:
    record = next(SyntheticDataGenerator(seed=20260820).generate(1, mode=OperatingMode.SHADOW))
    trace = PromiseGuardOrchestrator().evaluate(record.request)
    print(json.dumps(trace.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
