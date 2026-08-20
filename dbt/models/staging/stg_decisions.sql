select
    decision_id,
    event_id,
    order_id,
    trace ->> 'mode' as operating_mode,
    trace -> 'risk' ->> 'model_version' as model_version,
    cast(trace -> 'risk' ->> 'failure_probability' as numeric) as failure_probability,
    trace -> 'recommendation' ->> 'selected_action' as selected_action,
    cast(
        trace -> 'recommendation' ->> 'expected_incremental_value_vs_no_action'
        as numeric
    ) as expected_incremental_value,
    trace -> 'policy' ->> 'disposition' as policy_disposition,
    trace -> 'policy' ->> 'policy_version' as policy_version,
    trace -> 'policy' ->> 'control_version' as control_version,
    created_at
from {{ source('operational', 'decisions') }}
