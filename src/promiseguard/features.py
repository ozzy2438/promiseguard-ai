"""Point-in-time feature extraction shared by training and inference."""

from __future__ import annotations

from promiseguard.models import OrderContext

FEATURE_NAMES = (
    "inventory_reserved",
    "inventory_available",
    "inventory_confidence",
    "carrier_on_time_probability",
    "hours_since_expected_scan",
    "hours_to_promise",
    "alternative_location_available",
    "data_freshness_minutes",
    "gross_margin",
    "cancellation_cost",
    "support_cost",
    "is_vip",
    "restricted_product",
)


def extract_features(order: OrderContext) -> list[float]:
    hours_to_promise = (order.promised_delivery_at - order.evaluation_time).total_seconds() / 3_600
    return [
        float(order.inventory_reserved),
        float(order.inventory_available),
        order.inventory_confidence,
        order.carrier_on_time_probability,
        order.hours_since_expected_scan,
        hours_to_promise,
        float(order.alternative_location_available),
        float(order.data_freshness_minutes),
        float(order.gross_margin),
        float(order.cancellation_cost),
        float(order.support_cost),
        float(order.customer_segment == "VIP"),
        float(order.restricted_product),
    ]
