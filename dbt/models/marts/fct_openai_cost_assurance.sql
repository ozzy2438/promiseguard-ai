with runs as (
    select * from {{ ref('stg_openai_runs') }}
),
budget as (
    select * from {{ ref('stg_openai_budgets') }}
)
select
    r.run_id,
    r.decision_id,
    r.model,
    r.prompt_version,
    r.status,
    r.input_tokens,
    r.cached_input_tokens,
    r.output_tokens,
    r.total_tokens,
    r.reserved_cost_usd,
    r.actual_cost_usd,
    r.created_at,
    r.completed_at,
    r.error_code,
    b.limit_usd as project_limit_usd,
    b.spent_usd as project_accounted_spend_usd,
    b.remaining_usd as project_remaining_usd,
    case
        when r.status = 'COMPLETED' then true
        else false
    end as produced_validated_review,
    case
        when r.actual_cost_usd <= r.reserved_cost_usd then true
        else false
    end as stayed_within_reservation
from runs r
cross join budget b
