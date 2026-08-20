select
    outcome_id,
    decision_id,
    action_id,
    status as verification_status,
    on_time_delivery_observed,
    actual_intervention_cost,
    realised_gross_margin,
    estimated_incremental_value,
    verified_at
from {{ source('operational', 'outcomes') }}
