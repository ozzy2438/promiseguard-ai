with profiles as (
    select * from {{ ref('stg_autonomy_profiles') }}
),
evidence as (
    select
        action,
        count(*) as evidence_count,
        count(*) filter (where successful) as successful_evidence_count,
        count(*) filter (where not successful) as failed_evidence_count,
        count(*) filter (where compensated) as compensated_evidence_count,
        max(created_at) as latest_evidence_at
    from {{ ref('stg_autonomy_evidence') }}
    group by action
)
select
    profiles.action,
    profiles.level,
    profiles.verified_successes,
    profiles.consecutive_verified_successes,
    profiles.compensation_count,
    profiles.failure_count,
    profiles.reason,
    profiles.last_evidence_at,
    profiles.updated_by,
    profiles.updated_at,
    profiles.version,
    coalesce(evidence.evidence_count, 0) as evidence_count,
    coalesce(evidence.successful_evidence_count, 0) as successful_evidence_count,
    coalesce(evidence.failed_evidence_count, 0) as failed_evidence_count,
    coalesce(evidence.compensated_evidence_count, 0) as compensated_evidence_count,
    evidence.latest_evidence_at
from profiles
left join evidence using (action)
