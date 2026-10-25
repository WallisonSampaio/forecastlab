# Enterprise readiness (Phase 2)

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

Phase 1 runs 100% locally. The architecture is decoupled so each component can be swapped without rewriting the
product.

```text
Local DuckDB            →  PostgreSQL / Azure SQL / Snowflake (SQL kept ANSI-portable; db.py is the only adapter)
Local files             →  Data Lake (ADLS / S3 / GCS) via Parquet; ERP / SAP / Databricks ingestion jobs
Local Ollama            →  Enterprise LLM (Azure OpenAI / Bedrock / Vertex) behind the same llm.py interface
Local user              →  Microsoft Entra ID (OIDC) + RBAC
In-process jobs         →  Queue + workers (Celery / Azure Functions / Databricks jobs)
Docker Compose          →  AKS / Azure Container Apps / ECS, Terraform, CI/CD with environments
```

| Concern | Today | Enterprise path |
|---|---|---|
| Storage | DuckDB file | `db.py` adapter for PostgreSQL/Azure SQL; tables already normalised with version keys |
| Compute | Process pool per run | Distributed workers per series batch; same `process_series` function |
| Model governance | Model & run registries in DB | MLflow registry, approval gates |
| Data contracts | Validation module | Great Expectations / dbt tests on the lake |
| Identity | None (local) | Entra ID, RBAC per region/channel, row-level filters in the context layer |
| Observability | Logs | OpenTelemetry, run metrics dashboards |
| Delivery | GitHub Actions (lint, test, build) | Environments, image signing, Terraform plans |
