with decisions as (
    select * from {{ ref('stg_decisions') }}
),
actions as (
    select * from {{ ref('stg_actions') }}
),
outcomes as (
    select * from {{ ref('stg_outcomes') }}
)
select
    decisions.decision_id,
    decisions.order_id,
    decisions.created_at as decision_created_at,
    decisions.model_version,
    decisions.failure_probability,
    decisions.selected_action,
    decisions.policy_disposition,
    decisions.policy_version,
    decisions.control_version,
    decisions.expected_incremental_value,
    actions.action_id,
    actions.action_status,
    actions.expected_intervention_cost,
    outcomes.verification_status,
    outcomes.on_time_delivery_observed,
    outcomes.actual_intervention_cost,
    outcomes.realised_gross_margin as recorded_realised_margin_after_intervention,
    outcomes.estimated_incremental_value
from decisions
left join actions using (decision_id, order_id)
left join outcomes using (decision_id, action_id)
