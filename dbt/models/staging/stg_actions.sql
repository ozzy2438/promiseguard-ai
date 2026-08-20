select
    action_id,
    decision_id,
    order_id,
    action,
    status as action_status,
    cast(command ->> 'expected_intervention_cost' as numeric) as expected_intervention_cost,
    started_at,
    completed_at,
    error_code
from {{ source('operational', 'actions') }}
