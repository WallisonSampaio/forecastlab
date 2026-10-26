# Arquitetura

> ForecastLab · Desenvolvido por Wallison Sampaio — Especialista em Inteligência Comercial | Supply Chain | Data & AI
> Analytics · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

O ForecastLab é uma **aplicação full-stack local, modular e desacoplada**. Cada camada pode ser substituída de forma
independente quando o produto migrar para um ambiente corporativo (veja
[enterprise_readiness.md](enterprise_readiness.md)).

```text
                               FORECASTLAB
             Plataforma de Demand Planning e S&OP com IA

                                FRONTEND
               React 19 + TypeScript + Vite + Tailwind + ECharts
     Jornada: Entrada → Relatório executivo → Desvios   |   Ferramentas   |   Governança
                              │  REST (/api, JSON)
                              ↓
                            FastAPI
                              │
     ┌──────────────┬─────────┴────────┬───────────────────┬──────────────────────┐
     ↓              ↓                  ↓                   ↓                      ↓
  DuckDB     Motor de Forecast   Cenários / S&OP /   Motor de desvios       Storytelling
     │       (15 modelos,          FVA / alertas     (preço/volume/mix,     (relatório de 7
     │        backtest)                               causa raiz, ações)     capítulos, decisões,
     │                                                                       confiança)
     └──────────────┴──────────────────┴─────────┬─────────┴──────────────────────┘
                                                 ↓
                                         Camada Semântica
                                                 ↓
                              Analista de IA de Demanda  ──►  Ollama (LLM local)
```

## Módulos do backend (`backend/app`)

| Módulo | Responsabilidade |
|---|---|
| `api/` | Routers FastAPI: `data`, `forecast` (execuções, workspace, hierarquia, modelos, ajustes), `planning` (cenários, S&OP, FVA, alertas, IA, camada semântica), `export`, **`journey`** (`/api/journey`, `/api/models/trust`, `/api/story`) e **`deviations`** (`/api/deviations/*`) |
| `ingestion/` | Leitores de arquivo (xlsx/csv/parquet), schema canônico, nomes de colunas em PT/EN, modelo de planilha Excel |
| `validation/` | Diagnóstico da base, Score de qualidade dos dados, bloqueio por erros críticos, agregação mensal |
| `forecasting/` | Catálogo de modelos (15), perfil e classificação das séries, roteador de modelos candidatos, montagem do painel, worker por série, motor paralelo |
| `backtesting/` | Folds com origem móvel (rolling-origin), congelamento ex-ante dos drivers, limpeza de rupturas |
| `metrics/` | MAE, RMSE, MAPE, sMAPE, WMAPE, MASE, Viés, acurácia, classe de viés |
| `model_selection/` | Ranking, Campeão/Desafiante, confiança do modelo |
| `reconciliation/` | Reconciliadores bottom-up e top-down (interface de estratégia; MinT ainda como esboço) |
| `scenarios/` | Estimação de elasticidades, motor what-if, armazenamento e presets de cenários |
| `sop/` | Cockpit (referência numérica do relatório), motor de Viabilidade de metas, Alocação de metas |
| `fva/` | Forecast Value Added (ingênuo → estatístico → consenso) |
| `alerts/` | Regras da central de alertas, com explicações |
| **`deviations/`** | Motor do deep dive dos desvios (detalhes abaixo) |
| **`story/`** | Relatório executivo de 7 capítulos (detalhes abaixo) |
| `semantic_layer/` | Catálogo governado de métricas e dimensões + executor de consultas |
| `ai/` | Classificador de intenções, extração de entidades, handlers, NLG determinística, cliente Ollama, narração em segundo plano, roteamento de intenção pelo LLM, trava de fundamentação |
| `exports/` | Planilhas Excel e relatório executivo em HTML (renderiza o mesmo relatório de `story/`) |
| `services/` | Ciclo de vida das bases, jobs de execução, contexto de planejamento (visão consolidada e em cache), helpers de texto em pt-BR (`ptbr.py`) e **`trust.py`** (estado da jornada e confiança no forecast) |

### `deviations/` — deep dive dos desvios

| Arquivo | Responsabilidade |
|---|---|
| `common.py` | Comparações (`fc_pl`, `fc_tg`, `ac_pl`, `ac_fc`, `ac_cs`), períodos (`h`, `t1..t4`, `u12m`, `bt`, mês), níveis e rótulos, `DeviationError` (400/404 com mensagem em português) e o cache por contexto |
| `cells.py` | `plan_cells()`: células da lente Plano na **grade completa** séries × meses (orçamento sem venda conta como zero) |
| `plan.py` | Lente Plano: resumo, foco, exceções e ficha da série; ponte preço/volume/mix/eventos exata e aditiva, probabilidade de atingir a referência, Pareto e recorrência |
| `forecast_error.py` | `error_cells()` (backtest do campeão + drivers do mês e da origem) e a lente Previsão: WMAPE, viés, sistemático × ruído, sinal de rastreamento, ingênuo, erro por modelo e por antecedência, FVA |
| `rootcause.py` | Tags do plano, causa única por célula de erro (com travas de direção), grupos controlável/inerente, ações recomendadas e botões pré-preenchidos; todos os limites são constantes testadas |
| `narrative.py` | Títulos e frases de diagnóstico do deep dive, em pt-BR |
| `service.py` | Despacha cada chamada para `plan` ou `forecast_error` conforme a comparação |

### `story/` — relatório executivo

| Arquivo | Responsabilidade |
|---|---|
| `builder.py` | `build_story(ctx, filters)`: monta a ideia central, o SCQA e os 7 capítulos chamando os mesmos serviços do deep dive, da confiança e da viabilidade (uma única fonte de números) |
| `templates.py` | Helpers de formatação (`M`, `Ms`, `P1`, `P1s`, `P0`, `PP`, `MES`…) e um modelo de título e leituras por capítulo |
| `decisions.py` | Regras determinísticas D1–D8 do capítulo Decisões (top 5, impactos nunca somados) |

### `services/trust.py` — jornada e confiança

* `journey_status()`: etapa da jornada (`dados`, `modelos`, `pronto`), resumo da base ativa e estado da execução,
  inclusive a reexecução sobre uma base pronta. Sempre responde, mesmo sem base.
* `trust(ctx)`: acurácia fora da amostra, ganho sobre o ingênuo, vitórias por modelo, padrões de demanda, série
  mensal Real × Estatístico × Ingênuo, séries que pedem cautela e o veredito (`VERDICT_RULES`).

Os **códigos internos** (tipos de série, classificações, classes de viés, confiança, severidades, tipos de alerta,
tipos de cenário, comparações, status) continuam em inglês na API e são traduzidos apenas na exibição. Já os
**dados de demonstração** (regiões, canais, categorias, tipos de evento, planejadores) são gerados diretamente em
português, e todo texto gerado no backend (títulos, diagnósticos, avisos, erros) sai em pt-BR via
`services/ptbr.py`.

## Fluxo de uma requisição

1. O frontend chama `/api/...` (proxy do Vite em desenvolvimento, nginx no Docker).
2. Os endpoints de leitura constroem (ou reutilizam) um **PlanningContext** em cache — realizado, forecasts do
   campeão e do desafiante, ajustes → consenso, plano, backtests — para a *base ativa* e a *execução ativa*.
3. Os motores da jornada guardam seus resultados em um cache por contexto (`deviations.common.cached`): células
   base por comparação, junções do backtest, a confiança e o relatório por escopo. O cache é descartado inteiro
   quando o contexto muda.
4. Escritas (carga de arquivos, ajustes comerciais, cenários, execuções) invalidam o contexto — e, com ele, os
   caches da jornada e dos alertas.
5. As execuções de forecast rodam em uma thread em segundo plano; as séries são processadas em um **pool de
   processos** (uma thread BLAS por worker) e os resultados são gravados no DuckDB (registro de modelos, backtests,
   forecasts, perfis, registro de execuções).

Metas de tempo com cache quente na base de demonstração: `/api/journey` < 100 ms, `/api/models/trust` < 500 ms,
`/api/deviations/*` < 500 ms e `/api/story` < 1,5 s.

## Frontend (`frontend/src`)

| Pasta | Conteúdo |
|---|---|
| `pages/` | **Jornada:** `Entrada` (dados e modelos), `Relatorio` (7 capítulos), `Desvios` (deep dive). **Ferramentas:** `Forecasting` (Workspace de forecast), `Scenarios` (Cenários e metas, com a aba Alocação de metas), `Alerts`, `AIAnalyst`. **Governança:** `ModelPerformance` (Modelos e FVA; a aba FVA renderiza `FvaContent` de `FVA.tsx`), `Data` (Bases de dados). Mais a `Home` |
| `components/journey/` | `JourneyNav` (menu em três grupos com etapas e cadeados), `JourneyGate` (aviso "Antes do relatório, a confiança"), `RerunBanner` |
| `components/entrada/` | `Stepper`, `StepData` (demonstração, upload, resultado da validação), `StepModels`, `ModelScoreboard` (placar de vitórias), `StepTrust` (veredito, KPIs, gráfico, cautela) |
| `components/story/` | `ChapterRail`, `ChapterFrame`, `Storyline`, `Takeaways` (negrito sem HTML injetado), `ScopeSelect`, `DecisionTable`, `chapterVisuals` |
| `components/desvios/` | `ControlBar`, `Breadcrumb`, `KpiStrip`, `WherePanel`, `WhyPanel`, `WhenPanel`, `ExceptionsTable`, `SeriesDrawer`, `actions` (abrir, criar ajuste, simular, perguntar à IA) |
| `components/` | `Layout` (menu lateral, barra superior com pergunta à IA, cartão de autoria, modo apresentação), `Drawer`, `OverrideForm`, `GoalAllocation`, `RedirectWithSearch`, `FilterBar`, `DataTable`, `RunControls`, `data/health.tsx` (diagnóstico da base) e o kit de UI (`ui.tsx`) |
| `charts/` | Componente base do ECharts, TimelineChart, gráficos IBCS da jornada (`BridgeChart`, `VarianceColumns`, `VarianceBars`, `CauseBars`, `BacktestLine`, `FeasibilityRange`), barras/linhas/cascata/mapa de calor e o ChartRenderer da IA |
| `lib/` | `routes.ts` (construtores de rotas), `deviationsUrl.ts` (contrato de URL do deep dive), `ibcs.ts` (tokens de notação), `colors.ts`, `labels.ts`, `format.ts` (pt-BR), `branding.ts` |
| `hooks/` | `useJourney` (estado da jornada com polling durante a execução), `usePresentationMode`, utilitários do React Query, filtros globais (Zustand), debounce |
| `services/` | Cliente REST |
| `types/` | Contratos da API (`journey.ts`, `trust.ts`, `story.ts`, `deviations.ts`, `index.ts`) |

**Estado na URL.** O capítulo do relatório fica no caminho (`/app/relatorio/gap`) e o escopo na query; o deep dive
guarda lente, comparação, período, medida, caminho do detalhamento, nível, foco, causa, série aberta e capítulo de
origem na query (`lib/deviationsUrl.ts`), então qualquer visão pode ser recarregada ou compartilhada. Detalhar,
abrir a ficha e trocar a comparação entram no histórico do navegador (Voltar desfaz); focar, trocar período,
medida, nível ou causa substituem a entrada atual. As ferramentas continuam usando os filtros globais (Zustand);
os botões "Perguntar à IA", "Simular" e "Abrir no workspace" copiam o recorte do deep dive para esses filtros
antes de navegar.

**Rotas antigas.** Os endereços da antiga Visão Geral, do cockpit de S&OP e da tela de FVA redirecionam,
preservando a query, para o capítulo Resumo, o capítulo Meta e a aba FVA de Modelos e FVA; o antigo modo
hierarquia do Workspace abre o deep dive; a rota antiga `/app/settings` redireciona para a Entrada. A página de
Configurações foi removida e a API não expõe caminhos de arquivos locais (como o do banco DuckDB).

### Idioma e formatação

* Toda a interface está em **português do Brasil**. Os códigos da API são exibidos sempre via `lib/labels.ts`
  (ex.: `Seasonal` → "Sazonal", `REALISTIC` → "Realista", `High` → "Alta").
* `lib/format.ts` aplica o padrão brasileiro: `1.234`, `45,6 mil`, `12,34 mi`, `R$ 94,30 mi`, `+R$ 0,42 mi`,
  `14,8%`, `12,5 p.p.`, `dez/2026` e "dezembro de 2026", além da saudação por horário. `formatKpi` formata
  qualquer KPI montado no backend, e `lagLabel` escreve a antecedência do backtest ("1–3 meses").

### Sistema visual (soft UI premium)

* **Fundo** em gradiente pastel e **cards de vidro**: brancos translúcidos, `rounded-3xl`, borda branca e sombra
  difusa (`card` em `index.css`).
* **Cores da marca**: azul de ação `#3483FA`, navy `#2D3277` e amarelo sol `#FFE600`. Tokens em `index.css`:
  `text-ink`, `text-ink-2`, `text-muted`, `border-line`, `bg-plane`, `text-brand`, `text-navy`, `bg-sun`.
* **Ícones 3D**: `IconTile` cria um ladrilho com gradiente em 9 tons, usado nos títulos dos cards, nos KPIs das
  ferramentas e no menu. Os **KPIs da jornada não têm ícone** (decisão de *declutter*, e garante que "-R$ 11,70
  mi" caiba em 4 colunas a 1366 px).
* **KPIs**: `KpiCard` com tom pastel, valor, variação (`DeltaPill`) e dica; rótulos quebram linha livremente. No
  máximo 4 por linha (`sm:grid-cols-2 xl:grid-cols-4`).
* **Abas em pílula** (`Tabs`, `Segmented`), badges com rótulos em português e ícones lucide (`ClassBadge`,
  `BiasBadge`, `ConfidenceBadge`, `SeverityBadge`), `ProgressRing` e `ProgressBar`.
* **Sem faixas coloridas laterais** e **sem emoji** na jornada: o status é comunicado por superfície tingida,
  ícone e palavra.
* **Notação IBCS na jornada** (`lib/ibcs.ts`): Real sólido escuro, Ano anterior cinza, Orçamento em contorno, Meta
  em contorno tracejado, Forecast/Consenso hachurado; variação favorável/desfavorável em verde/vermelho sempre com
  sinal; erro de previsão "Superestimou" (vermelho) / "Subestimou" (azul), nunca verde; causas controláveis em azul
  da marca, inerentes em cinza e sem causa em hachura cinza. Gráficos sem linhas de grade, com rótulos diretos,
  `aria-label` e o botão "Ver tabela".
* **Cores das ferramentas**: os gráficos fora da jornada usam os cinco primeiros slots de uma paleta categórica
  validada (ΔE ≥ 8 entre cores vizinhas para daltonismo): Estatístico = azul, Orçamento = laranja, Consenso =
  verde-água, Meta = amarelo, Desafiante = magenta, Real = tinta escura. Escala sequencial em azul para os mapas de
  calor de WMAPE; escala divergente azul ↔ vermelho para o viés.

As regras de orçamento visual (blocos por página, títulos, idioma) são verificadas por
`frontend/src/test/journey.global.test.tsx`; veja [jornada.md](jornada.md).

## Topologia de execução

| Modo | Componentes |
|---|---|
| Desenvolvimento local | `uvicorn` em :8000, servidor do Vite em :3000 (proxy `/api`), Ollama opcional em :11434 |
| Docker | `frontend` (nginx :3000 → `/api` → backend), `backend` (:8000, DuckDB em volume nomeado), `ollama`, `ollama-pull` |

## Decisões de design

* **DuckDB** — armazenamento analítico sem infraestrutura; SQL mantido portável para PostgreSQL / Azure SQL.
* **Backtests ex-ante** — os drivers futuros nunca são revelados aos modelos, então a acurácia medida é honesta.
* **Uma fonte de números** — relatório, deep dive, exportação HTML e cockpit usam as mesmas funções; testes de
  consistência garantem que o mesmo número é igual em todas as telas.
* **Um payload por relatório** — `/api/story` traz os 7 capítulos de uma vez; trocar de capítulo é instantâneo.
* **Regras determinísticas para decisões e causas** — limites nomeados e testados; nenhum número do relatório é
  gerado por IA.
* **Os motores calculam, a IA explica** — a resposta calculada aparece na hora; o LLM local só reescreve o texto
  em segundo plano, protegido por travas de fundamentação, de classificação e de direção.
* **Reconciliação bottom-up** — números coerentes em todos os níveis da hierarquia por construção.
* **Códigos em inglês, exibição em português** — contratos de API estáveis e interface 100% localizada.
