from __future__ import annotations

import sys
from types import SimpleNamespace

from promiseguard.openai_agent import OpenAIResponsesClient
from promiseguard.openai_models import AgentDecisionReview


def test_official_sdk_adapter_uses_structured_non_stored_single_request(monkeypatch) -> None:
    captured = {}
    review = AgentDecisionReview(
        decision_id="dec-test",
        selected_action="REROUTE",
        policy_disposition="REQUEST_APPROVAL",
        next_step="SUBMIT_DECISION",
        rationale_codes=("HIGHEST_EXPECTED_VALUE", "APPROVAL_REQUIRED"),
        evidence_ids=("oms:record:2026-08-20T00:00:00+00:00",),
        requires_human_attention=True,
        uncertainty=0.1,
        summary="The governed recovery is supported by immutable evidence.",
    )

    class FakeResponses:
        def parse(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                id="resp-test",
                output_parsed=review,
                usage=SimpleNamespace(
                    input_tokens=100,
                    output_tokens=30,
                    total_tokens=130,
                    input_tokens_details=SimpleNamespace(cached_tokens=10),
                ),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAIResponsesClient(timeout_seconds=12)
    response = client.parse_review(
        model="gpt-5-nano",
        instructions="bounded",
        input_text="{}",
        max_output_tokens=320,
        idempotency_key="request-key",
        decision_id="dec-test",
    )

    assert captured["client"] == {"timeout": 12, "max_retries": 0}
    kwargs = captured["kwargs"]
    assert kwargs["text_format"] is AgentDecisionReview
    assert kwargs["store"] is False
    assert kwargs["max_output_tokens"] == 320
    assert kwargs["reasoning"] == {"effort": "minimal"}
    assert kwargs["extra_headers"] == {"Idempotency-Key": "request-key"}
    assert response.usage.cached_input_tokens == 10
