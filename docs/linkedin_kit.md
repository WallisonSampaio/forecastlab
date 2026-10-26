# Kit de portfólio para o LinkedIn

> ForecastLab · Desenvolvido por Wallison Sampaio — Especialista em Inteligência Comercial | Supply Chain | Data & AI
> Analytics · [www.linkedin.com/in/wallisonsampaio](https://www.linkedin.com/in/wallisonsampaio)
>
> *Developed by Wallison Sampaio — Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist*

## Chamada principal

> **Construí o ForecastLab — uma plataforma full-stack de Demand Planning e S&OP com IA que faz o backtest de vários
> modelos de forecast, escolhe o melhor modelo por SKU/cliente, simula cenários comerciais e avalia se as metas do
> negócio são estatisticamente realistas.**

*EN:* I built ForecastLab — a full-stack AI-powered Demand Planning & S&OP platform that backtests multiple
forecasting models, selects the best model per SKU/customer, simulates commercial scenarios and evaluates whether
business targets are statistically realistic.

## Rascunho do post (PT-BR)

Construí o **ForecastLab**, uma plataforma de decisão para Demand Planning e S&OP com IA — 100% local, sem nenhuma
API paga e totalmente em português.

🔹 15 modelos de forecast competem por Cliente × SKU em um backtest rolling-origin (sem vazamento de dados)
🔹 Campeão e Desafiante, confiança do modelo e forecast probabilístico P10/P50/P90
🔹 Ajustes comerciais → forecast de consenso, e FVA para provar se os ajustes agregam valor
🔹 Simulações what-if com elasticidades estimadas a partir do histórico
🔹 "Esta meta é realista?" — probabilidade, checagem do P90, crescimento exigido e a alavanca que fecharia o gap
🔹 Uma jornada guiada: Entrada (dados, modelos e um veredito de confiança) → Relatório executivo em 7 capítulos
(storytelling com Pirâmide de Minto e notação IBCS) → Deep dive dos desvios (ponte preço/volume/mix e causa raiz do
erro, controlável × inerente)
🔹 Um analista de IA local (Ollama) que entende perguntas livres em português — *"quanto vamos vender de Bebidas no
Sul em dezembro?"* —, responde na hora com números calculados e é proibido de inventar números
🔹 Interface premium em soft UI: cards de vidro, KPIs em tons pastel, um visual por capítulo do relatório e uma barra de
perguntas à IA em todas as telas

Stack: React + TypeScript · FastAPI · DuckDB · statsmodels / scikit-learn · ECharts · Docker.
Todos os dados são sintéticos. Código no GitHub 👇

#DemandPlanning #SOP #SupplyChain #InteligenciaComercial #DataScience #IA

## Post draft (EN)

I built **ForecastLab**, an AI Demand Planning & S&OP decision platform — 100% local, zero paid APIs, with a fully
Brazilian Portuguese interface.

🔹 15 forecasting models compete per Customer × SKU in a rolling-origin backtest (no data leakage)
🔹 Champion & Challenger, model confidence, P10/P50/P90 forecasts
🔹 Commercial overrides → consensus, and FVA to prove whether overrides add value
🔹 What-if scenarios with elasticities estimated from history
🔹 "Is this target realistic?" — probability, P90 check, required growth and the lever that would close the gap
🔹 A guided journey: Entry (data, models and a trust verdict) → 7-chapter executive report (Minto pyramid storytelling,
IBCS notation) → deviation deep dive (price/volume/mix bridge and forecast-error root cause, controllable vs
inherent)
🔹 A local AI analyst (Ollama) that understands free natural-language questions in Portuguese, answers instantly
with computed numbers — and is not allowed to invent numbers
🔹 Premium soft-UI design: glassy cards, pastel KPI cards, one visual per report chapter and an AI question bar on
every screen

Stack: React + TypeScript · FastAPI · DuckDB · statsmodels / scikit-learn · ECharts · Docker.
All data is synthetic. Code on GitHub 👇

## Capturas de tela

| Arquivo | Tela |
|---|---|
| `screenshots/relatorio-resumo.png` | **Destaque** — Relatório executivo: ideia central, SCQA e KPIs |
| `screenshots/entrada.png` | Entrada: competição de modelos e veredito de confiança |
| `screenshots/relatorio-gap.png` | Relatório executivo: quem explica o gap vs orçamento |
| `screenshots/desvios-plano.png` | Deep dive dos desvios — lente Plano (ponte preço/volume/mix) |
| `screenshots/desvios-previsao.png` | Deep dive dos desvios — lente Previsão (causas do erro) |
| `screenshots/forecast-workspace.png` | Workspace de forecast: P10–P90, campeão e ajustes |
| `screenshots/model-performance.png` | Modelos e FVA: ranking e campeão vs desafiante |
| `screenshots/scenarios.png` | Cenários e metas: Base vs Agressivo |
| `screenshots/ai-analyst.png` | Analista de IA respondendo "A meta é realista?" |
| `screenshots/alerts.png` | Central de alertas com "Investigar no deep dive" |

Gere as capturas novamente com `scripts/capture_screenshots.ps1` depois de qualquer mudança visual.

## Roteiro de vídeo (60–120 s)

| Cena | Tela | Narração |
|---|---|---|
| 1 | Home → "Começar" | "ForecastLab — Demand Planning e S&OP com IA." |
| 2 | Entrada → "Enviar minha planilha" com `forecastlab_sample_upload.xlsx` (regiões Sul e Centro-Oeste) | "Carrego o histórico em Excel…" |
| 3 | Entrada → resultado da validação e score de qualidade | "…validado: score de qualidade, e erros críticos bloqueiam o forecast." |
| 4 | Entrada → competição de modelos (progresso e placar) | "15 modelos competem em cada série, fora da amostra." |
| 5 | Entrada → veredito de confiança | "Antes da história, a confiança: o forecast merece crédito?" |
| 6 | Relatório → Resumo (ideia central + SCQA) | "A mensagem da reunião em uma frase, com números." |
| 7 | Relatório → Gap vs orçamento | "Quem explica o gap — e se é premissa ou demanda." |
| 8 | "Investigar no deep dive" → clique em um cliente → ponte preço/volume/mix | "Onde, por quê e quando desviamos." |
| 9 | Ficha da série → "Criar ajuste comercial" | "Da causa à ação: o consenso é recalculado." |
| 10 | Relatório → Meta → "Simular alavanca" | "A meta é realista? Probabilidade, gap e a alavanca que fecharia." |
| 11 | "Perguntar à IA" → *"A meta é realista?"* | "A IA explica o risco — com os números calculados pelos motores." |
| Fim | Cartão de assinatura | **ForecastLab — Desenvolvido por Wallison Sampaio** |
