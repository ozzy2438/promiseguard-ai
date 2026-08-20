select
    control_key,
    enabled,
    reason,
    updated_by,
    updated_at,
    version
from {{ source('operational', 'runtime_controls') }}
