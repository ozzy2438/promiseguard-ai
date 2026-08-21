select
    budget_key,
    cast(limit_usd as numeric(14, 6)) as limit_usd,
    cast(reserved_usd as numeric(14, 6)) as reserved_usd,
    cast(spent_usd as numeric(14, 6)) as spent_usd,
    cast(limit_usd - reserved_usd - spent_usd as numeric(14, 6)) as remaining_usd,
    updated_at,
    version
from {{ source('operational', 'openai_budgets') }}
