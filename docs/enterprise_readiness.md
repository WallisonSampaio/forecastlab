# Prontidão enterprise (Fase 2)

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

A Fase 1 roda 100% localmente. A arquitetura é desacoplada para que cada componente possa ser trocado sem reescrever
o produto.

```text
DuckDB local            →  PostgreSQL / Azure SQL / Snowflake (SQL mantido portável em ANSI; db.py é o único adaptador)
Arquivos locais         →  Data Lake (ADLS / S3 / GCS) via Parquet; jobs de ingestão de ERP / SAP / Databricks
Ollama local            →  LLM corporativo (Azure OpenAI / Bedrock / Vertex) atrás da mesma interface llm.py
Usuário local           →  Microsoft Entra ID (OIDC) + RBAC
Jobs no mesmo processo  →  Fila + workers (Celery / Azure Functions / jobs do Databricks)
Docker Compose          →  AKS / Azure Container Apps / ECS, Terraform, CI/CD com ambientes
```

| Tema | Hoje | Caminho enterprise |
|---|---|---|
| Armazenamento | Arquivo DuckDB | Adaptador `db.py` para PostgreSQL/Azure SQL; tabelas já normalizadas com chaves de versão |
| Processamento | Pool de processos por execução | Workers distribuídos por lote de séries; a mesma função `process_series` |
| Governança de modelos | Registro de modelos e de execuções no banco | Registro no MLflow, etapas de aprovação |
| Contratos de dados | Módulo de validação (Diagnóstico da base) | Great Expectations / testes do dbt no data lake |
| Identidade | Nenhuma (uso local) | Entra ID, RBAC por região/canal, filtros por linha na camada de contexto |
| Observabilidade | Logs | OpenTelemetry, dashboards de métricas das execuções |
| Entrega | GitHub Actions (lint, testes, build) | Ambientes, assinatura de imagens, planos do Terraform |
| Idioma | Interface em português do Brasil, códigos internos em inglês | Internacionalização (i18n) com catálogo de traduções por usuário |
