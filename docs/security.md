# Security (future enterprise version)

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

The Portfolio MVP is a single-user local application with synthetic data. It intentionally has no authentication.
This document lists what an enterprise deployment adds.

| Topic | Plan |
|---|---|
| Authentication | OIDC with Microsoft Entra ID; FastAPI dependency validating JWTs; frontend MSAL |
| Authorization / RBAC | Roles: Viewer, Demand Planner, Commercial (overrides), S&OP Lead (approve), Admin. Row-level scope (region/channel/customer) enforced in the planning-context filter layer |
| Secrets management | Azure Key Vault / AWS Secrets Manager; no secrets in images; managed identities for DB and LLM |
| Audit logs | Append-only audit table for uploads, overrides, scenario changes, run activations and approvals (who/when/what/before/after) |
| Encryption | TLS everywhere; encryption at rest for DB and lake; customer-managed keys where required |
| Data protection | PII-free by design (customer accounts, not individuals); data retention per dataset version |
| LLM safety | Enterprise LLM endpoint inside the tenant; prompts contain aggregated facts only; numeric grounding guard kept; no training on company data |
| Supply chain | Pinned dependencies, SCA in CI, signed images |
| Upload hardening | Size limit (`FORECASTLAB_MAX_UPLOAD_MB`), type allow-list, server-side parsing only |
