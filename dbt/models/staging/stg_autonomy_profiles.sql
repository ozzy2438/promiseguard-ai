select
    action,
    level,
    verified_successes,
    consecutive_verified_successes,
    compensation_count,
    failure_count,
    reason,
    last_evidence_at,
    updated_by,
    updated_at,
    version
from {{ source('operational', 'autonomy_profiles') }}
