# AWS readiness (not deployed)

PromiseGuard AI is **not** deployed to AWS. This note prepares a future deployment after local
and pre-pilot gates are satisfied. Do not apply it. Do not create cloud resources from this
repository unless the owner explicitly instructs it.

## Target shape

A single modular monolith remains the unit of deployment.

| Concern | Intended AWS service | Notes |
|---|---|---|
| Compute | ECS Fargate behind an Application Load Balancer | One API task definition; optional second console service |
| Database | Amazon RDS PostgreSQL | Alembic remains the migration tool; no SQLite in AWS |
| Secrets | AWS Secrets Manager | `OPENAI_API_KEY`, DB credentials, future OMS/WMS/carrier secrets |
| Networking | VPC with private subnets | API and RDS private; ALB public or private depending on SSO |
| Identity | IAM task roles + later SSO | Application RBAC stays in PromiseGuard; IAM is infrastructure identity |
| Logs | CloudWatch Logs | JSON logs already emitted by the API |
| Metrics | CloudWatch / Prometheus remote write | Existing `/metrics` scrape |
| Alerting | CloudWatch alarms | Kill-switch active, budget remaining, 5xx, RDS storage |
| Backup | RDS automated backups + PITR | Evidence ledgers are the recovery unit |
| Cost controls | Budgets + the in-app US$3 OpenAI ceiling | Platform spend is separate from application OpenAI accounting |
| CI/CD | GitHub Actions → ECR → ECS | Promote only after local-stack and quality jobs are green |

## Explicit non-goals for this phase

- No Terraform apply.
- No account, VPC, RDS instance, ECS cluster or hosted zone.
- No AWS cost incurred by this engineering phase.
- No claim that the application is deployment-ready.

## Suggested later Terraform layout (unapplied)

When the owner authorises infrastructure work, start with modules for VPC, RDS, ECS and secrets.
Keep state in an owner-controlled backend. Preview and production should be separate accounts or
at least separate VPCs. Until then, local Docker Compose is the production-like runtime.
