select
    evidence_id,
    action,
    evidence_kind,
    successful,
    compensated,
    created_at
from {{ source('operational', 'autonomy_evidence') }}
