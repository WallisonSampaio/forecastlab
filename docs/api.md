# API REST

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

Documentação OpenAPI interativa: **http://localhost:8000/docs**.

Os filtros de hierarquia são parâmetros de query aceitos pela maioria dos endpoints de leitura: `region`, `channel`,
`customer`, `category`, `brand`, `sku` (repetíveis). `measure` = `units` (unidades) | `revenue` (receita).

> **Convenção de idioma:** caminhos, parâmetros, nomes de campos e códigos internos (tipos de série,
> classificações, classes de viés, confiança, severidades, tipos de alerta, tipos de cenário, status, nomes de
> modelos, comparações `fc_pl`/`ac_fc`…) ficam em inglês para manter o contrato estável. Os textos voltados ao
> usuário (títulos, explicações, alertas, justificativas, diagnósticos, avisos, respostas da IA e mensagens de
> erro em `detail`) já saem em português, e a interface traduz os códigos com `lib/labels.ts`. Os valores dos
> dados de demonstração (regiões, canais, categorias, tipos de evento, planejadores) são em português.

**Erros comuns**

| Status | Quando |
|---|---|
| 400 | parâmetro inválido (`detail` em português, ex.: "Período inválido para esta comparação.") |
| 404 | recurso inexistente (ex.: "Série 'Litoral Market · SKU-10101' não encontrada") |
| 409 | sem base ativa (`code: "no_dataset"`) ou sem execução de forecast concluída ("Ainda não há uma execução de forecast concluída. Execute o forecast primeiro.") |
| 413 | arquivo maior que o limite de upload (padrão 50 MB) |
| 422 | corpo ou query malformados ("Requisição inválida. Verifique o(s) campo(s): …") |

## Sistema

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/health` | status, base ativa, job em execução |
| GET | `/api/meta` | informações do app, autoria/marca, catálogo de modelos, horizontes, status da IA (espera no máximo 0,5 s pelo Ollama; sem caminhos de arquivos locais) |

## Jornada (Entrada → Relatório → Desvios)

Os três endpoints que alimentam a jornada guiada. Veja o racional em [jornada.md](jornada.md).

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/journey` | etapa da jornada, base ativa e estado da execução. **Sempre HTTP 200**, mesmo sem base |
| GET | `/api/models/trust` | quanto o forecast merece crédito: acurácia fora da amostra, vitórias por modelo, confiança e veredito |
| GET | `/api/story` | o relatório executivo de 7 capítulos (receita), da empresa toda ou de um recorte (filtros) |

### `GET /api/journey`

```text
stage    "dados" (sem base ativa) | "modelos" (base ativa sem execução concluída) | "pronto" (execução concluída)
dataset  null | {version, name, status (valid|warnings|blocked), quality_score, quality_label, n_series,
                 n_customers, n_skus, start_date, end_date, n_months, plan_source, plan_derived, has_plan,
                 n_critical, n_warnings, has_overrides_history}
run      {state (none|running|failed|completed), run_id, progress, step, done, total, message,
          finished_at, duration_s, rerunning}
```

`rerunning = true` quando uma nova execução roda sobre uma base que já tem execução concluída: a interface
continua mostrando os números da execução ativa, com um aviso.

### `GET /api/models/trust`

Sem execução: `{available: false, reason}` (HTTP 200). Com execução:

| Campo | Conteúdo |
|---|---|
| `run` | `run_id, finished_at, duration_s, n_series, n_models, n_folds, fold_horizon, horizon, avg_candidates, backtest_start, backtest_end, n_fallback, lag_label` ("1–3 meses") |
| `accuracy`, `wmape`, `bias`, `bias_class`, `bias_label` | erro fora da amostra do campeão, em unidades |
| `naive_wmape`, `gain_vs_naive_pp`, `error_reduction_vs_naive` | comparação com o método ingênuo |
| `consensus_wmape`, `fva_pp` | consenso histórico e FVA (`null` sem histórico de ajustes) |
| `wmape_by_lag` | WMAPE por antecedência (1, 2, 3 meses…) |
| `confidence_series`, `confidence_revenue_share` | séries e receita prevista por confiança (Alta/Média/Baixa) |
| `champions` | vitórias por modelo (`model, label, family, family_label, series, share, wmape_won, is_reference`) |
| `by_pattern`, `pattern_insight` | modelo mais vencedor por padrão de demanda e a frase-resumo |
| `backtest_monthly` | Real, Estatístico e Ingênuo por mês fora da amostra (R$) |
| `caution` | até 5 séries de baixa confiança ou WMAPE ≥ 35%, por receita prevista |
| `verdict` | `{code, label, headline, reasons[]}`, com `code` = `confiavel` \| `cautela` \| `nao_confiavel` |

Regras do veredito: **confiável** com acurácia ≥ 80%, |viés| ≤ 5%, receita em séries de confiança baixa ≤ 20% e
ganho sobre o ingênuo > 0; **cautela** com acurácia ≥ 65%, |viés| ≤ 10% e ganho > 0; **não confiável** nos demais
casos.

### `GET /api/story`

Parâmetros: os filtros (a interface usa uma dimensão entre `region`, `channel` e `category`). A medida é sempre
receita. Sem execução: `{available: false, reason}`.

```text
reference         {cycle_label, last_actual, horizon_label, horizon_months, ltm_label, backtest_label, lag_label,
                   scope_label, dataset_version, run_id, plan_source, plan_derived, has_plan}
governing_thought ideia central (Pirâmide de Minto)
scqa              {situacao, complicacao, resposta}
chapters[7]       resumo, realizado, precisao, projecao, gap, meta, decisoes (ordem fixa), cada um com
                  {id, index, title, short, question, headline, context, takeaways[≤3], status (ok|empty), notice,
                   visual {kind, data}, investigate {label, params}, secondary_action, ask_ai, facts}
```

`visual.kind` ∈ `kpis`, `bridge`, `cause_bars`, `monthly_variance`, `variance_bars`, `feasibility_range`,
`decision_table`. `investigate.params` segue o contrato de URL do deep dive (`cmp`, `periodo`, `nivel`, `sel`…).
`facts` guarda os números crus usados no título e no visual (fonte única, testada). Um capítulo sem os dados
necessários (ex.: base sem orçamento) volta com `status: "empty"` e um `notice` em português.

## Deep dive dos desvios

Todos são `GET`, aceitam os filtros de hierarquia (o caminho do detalhamento) e exigem uma execução concluída (409
sem ela). A lente é derivada da comparação.

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/deviations/summary` | título, 4 KPIs, avisos, opções de período/comparação/nível, quebra por membro ("Onde está o desvio?") e concentração (Pareto) |
| GET | `/api/deviations/focus` | ponte preço/volume/mix ou causas do erro, série mensal, trimestres, diagnóstico (2–3 frases) e ações, para o recorte ou para um membro em foco |
| GET | `/api/deviations/exceptions` | séries Cliente × SKU que merecem ação, ordenadas por impacto, com causa, ação recomendada e botões |
| GET | `/api/deviations/series` | ficha da série: cabeçalho, resumo, linha do tempo de 24 meses, evidências mês a mês, efeitos, ação recomendada e ajustes futuros |

**Comparações (`cmp`, obrigatório)**

| `cmp` | Lente | Comparação | Períodos aceitos (`period`) | Padrão |
|---|---|---|---|---|
| `fc_pl` | Plano | Consenso × Orçamento | `h` (horizonte), `t1`…`t4` (trimestres), `YYYY-MM` do horizonte | `h` |
| `fc_tg` | Plano | Consenso × Meta | idem | `h` |
| `ac_pl` | Plano | Real × Orçamento | `u12m` (últimos 12 meses), `YYYY-MM` dos últimos 12 meses | `u12m` |
| `ac_fc` | Previsão | Real × Estatístico (campeão), fora da amostra | `bt` (janela de backtest), `YYYY-MM` do backtest | `bt` |
| `ac_cs` | Previsão | Real × Consenso histórico (com ajustes) | idem | `bt` |

**Parâmetros**

| Parâmetro | Endpoints | Valores |
|---|---|---|
| `cmp` | todos | ver tabela acima |
| `period` | todos | ver tabela acima |
| `measure` | todos | `revenue` (padrão) \| `units`; a lente Previsão usa sempre receita para o impacto (o WMAPE é em unidades) |
| `level` | summary, focus, exceptions | nível da quebra: `region`, `channel`, `customer`, `category`, `brand`, `sku`, `series`; na lente Previsão também `champion` e `series_type`. Padrão: o primeiro de Região → Canal → Cliente → Categoria → SKU ainda não filtrado |
| `limit` | summary (1–100, padrão 12), exceptions (1–200, padrão 15) | linhas devolvidas |
| `focus_level`, `focus` | focus, exceptions | membro em foco (ex.: `focus_level=customer&focus=Litoral Market`) |
| `direction` | exceptions | `adverse` (padrão), `favorable`, `all` — lente Plano |
| `cause` | exceptions | código de causa (ex.: `promocao`) — lente Previsão |
| `offset` | exceptions | paginação ("Ver mais") |
| `series_id` | series | `Cliente\|SKU`, ex.: `Litoral Market\|SKU-10101` (a ficha não usa os filtros) |

**Validação (HTTP 400, `detail` em português):** comparação inválida ("Comparação inválida. Use fc_pl, fc_tg,
ac_pl, ac_fc ou ac_cs."), período fora da janela da comparação ("Período inválido para esta comparação."), nível
inválido ("Nível inválido para esta comparação."), medida, direção ou causa inválidas. Série desconhecida: 404.

**Capacidade indisponível (HTTP 200 com `available: false` e `reason`):** comparação de plano sem orçamento/meta
("Não há orçamento/meta nesta base.") e `ac_cs` sem histórico de ajustes ("Sem histórico de ajustes comerciais
nesta base."). Avisos não bloqueantes chegam em `notices` (orçamento estimado automaticamente, orçamento parcial
no período, poucos meses de backtest, séries sem backtest).

**Formato da resposta (resumo)**

```text
summary    {available, cmp, lens (plan|forecast), measure, period {code, label, months, kind}, periods[], comparisons[],
            node {label, path[], n_series}, headline, notices[], kpis[4], breakdown {level, level_label, next_level,
            levels[], rows[], others, n_members}, concentration {n_top, share, members, n_members} | null}
focus      {available, cmp, lens, measure, period, focus {level, member, label}, headline, bridge[] | null,
            drivers | null, causes[] | null, split | null, by_model[] | null, fva | null, monthly[], quarters[] | null,
            diagnosis[], actions[]}
exceptions {total, rows[] {series_id, label, customer, sku, product, region, channel, category, impact,
            x/p/variance/variance_pct/prob_hit (plano) | abs_error/wmape/bias/tracking_signal (previsão),
            top_cause, confidence, champion, series_type_label, tags[], recommended_action, actions[]}}
series     {series_id, label, header, summary, timeline[], evidence[] | null, months[] | null, effects | null,
            tags[], recommended_action, actions[], future_overrides[]}
```

As linhas da quebra no plano trazem `x, p, variance, variance_pct, share_of_adverse, cum_share, prob_hit,
growth_plan, growth_fc, realized_variance_pct, effects {volume, mix, price, events}, tags[], is_exception,
drillable`; na previsão, `actual, forecast, abs_error, net_error, wmape, bias, systematic, noise, share, cum_share,
top_cause`. As fórmulas (ponte preço/volume/mix, probabilidade, Pareto, causas do erro) estão em [sop.md](sop.md).

Exemplo:

```bash
curl "http://localhost:8000/api/deviations/summary?cmp=fc_pl&level=customer"
curl "http://localhost:8000/api/deviations/focus?cmp=fc_pl&focus_level=customer&focus=Litoral%20Market"
curl "http://localhost:8000/api/deviations/exceptions?cmp=ac_fc&cause=promocao&limit=15"
curl "http://localhost:8000/api/deviations/series?cmp=ac_fc&series_id=Litoral%20Market%7CSKU-10101"
```

## Dados

| Método | Caminho | Descrição |
|---|---|---|
| POST | `/api/data/upload` | arquivo multipart (`file`: `.xlsx`, `.csv` ou `.parquet`; `.xls` antigo exige o pacote opcional `xlrd`) + `run_forecast` (padrão `true`) → `{file_name, validation, quality_label, accepted, dataset_version, run_id, run_message?}`. Base com erros críticos: `accepted: false` e nada é gravado (a base anterior continua ativa). Base aceita durante uma execução: é gravada e ativada, mas `run_id` volta `null` com a explicação em `run_message` |
| POST | `/api/data/demo` | `{seed, run_forecast}` — gera e ativa a base sintética; 409 se houver execução em andamento |
| GET | `/api/data/datasets` | versões da base |
| GET | `/api/data/active` | base ativa + Diagnóstico da base |
| POST | `/api/data/datasets/{version}/activate` | troca a base ativa (409 para base bloqueada) |
| GET | `/api/data/template` | modelo de planilha Excel |
| GET | `/api/data/preview` | linhas (limit/offset/filtros) |
| GET | `/api/data/dimensions` | membros da hierarquia, lista de séries, horizonte |
| GET | `/api/data/eda` | análise exploratória: tendência, sazonalidade, volatilidade, efeitos de promoção e de distribuição |
| GET | `/api/data/profiles` | perfil e classificação das séries |

## Forecast

| Método | Caminho | Descrição |
|---|---|---|
| POST | `/api/forecast/run` | `{horizon, n_folds, fold_horizon, clean_stockouts, run_all_models, models}` |
| GET | `/api/forecast/job` | progresso do job na fila ou em execução (ou `null`) |
| GET | `/api/forecast/runs` · `/api/forecast/runs/{id}` | Registro de execuções |
| POST | `/api/forecast/runs/{id}/activate` | usa uma execução anterior |
| GET | `/api/forecast/models` | catálogo de modelos |
| GET | `/api/forecast/series` | séries com campeão, WMAPE, viés, últimos 12 meses (U12M) e forecast de 12 meses |
| GET | `/api/forecast/series-detail?series_id=` | dados do workspace: cabeçalho, seleção, próximo mês e intervalo, linha do tempo, ranking de modelos, backtest, ajustes |
| GET | `/api/forecast/aggregate` | linha do tempo e KPIs agregados para qualquer nó da hierarquia |
| GET | `/api/forecast/hierarchy?level=&method=bottom_up\|top_down` | tabela de drill-down (na interface, a navegação pela hierarquia acontece no deep dive dos desvios) |

## Modelos

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/models/leaderboard` | ranking de modelos (WMAPE medido só nas séries em que cada modelo competiu) |
| GET | `/api/models/distribution` | campeões por modelo, família e confiança |
| GET | `/api/models/heatmap?metric=wmape\|bias` | mapa de calor |
| GET | `/api/models/performance` | campeão × desafiante por série |
| GET | `/api/models/registry?series_id=&limit=` | registro de modelos |
| GET | `/api/models/trust` | veja [Jornada](#get-apimodelstrust) |

## Ajustes comerciais

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/overrides` | ajustes cadastrados |
| GET | `/api/overrides/event-library` | biblioteca de eventos (uplift padrão por tipo) |
| POST | `/api/overrides` | `{customer?, sku?, date, event_type, uplift_pct, comment, created_by}` |
| PUT · DELETE | `/api/overrides/{id}` | edita ou remove um ajuste |

`event_type` usa os tipos da biblioteca de eventos em português: "Promoção", "Merchandising", "Ganho de
distribuição", "Perda de distribuição", "Nova loja", "Ganho de cliente", "Perda de cliente", "Campanha", "Mudança de
preço", "Lançamento", "Deslistagem", "Ação de concorrente". O deep dive envia esse mesmo `POST` a partir do botão
"Criar ajuste comercial", com os campos pré-preenchidos pela causa do desvio.

## Cenários

| Método | Caminho | Descrição |
|---|---|---|
| GET · POST | `/api/scenarios` | lista (cria os presets) · cria um cenário |
| PUT · DELETE | `/api/scenarios/{id}` | edita ou remove (presets são protegidos: 403) |
| POST | `/api/scenarios/{id}/duplicate` | duplica |
| POST | `/api/scenarios/simulate` | `{params, filters}` → resultado do what-if |
| GET | `/api/scenarios/compare?ids=&measure=` | comparação de cenários |
| GET | `/api/scenarios/elasticities` | elasticidades estimadas (e o gabarito da base sintética) |

Parâmetros do cenário: `price_change_pct, distribution_change_pct, promo_months[], promo_discount_pct,
merch_months[], marketing_change_pct, customer_growth_pct, market_growth_pct, scope{}, base (consensus|statistical)`.

## S&OP, FVA e alertas

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/overview` | resumo usado pela Home (a antiga tela Visão Geral foi substituída pelo relatório executivo) |
| GET | `/api/sop/cockpit` | real, estatístico, consenso, orçamento, meta, gaps, risco/oportunidade e visão trimestral. A interface não o consome mais diretamente, mas ele é a referência numérica dos capítulos Próximos meses e Gap (testado) |
| GET | `/api/sop/feasibility?months=&measure=` | viabilidade da meta, curva de probabilidade e viabilidade por cliente |
| POST | `/api/sop/allocation` | `{dimension, method, total_target?, weights?, filters, measure}` — alocação de metas |
| GET | `/api/fva` | Forecast Value Added (escada ingênuo → estatístico → consenso, por tipo de evento, planejador…) |
| GET | `/api/alerts?severity=&type=` | central de alertas (resumo + lista) |

## IA e camada semântica

| Método | Caminho | Descrição |
|---|---|---|
| POST | `/api/ai/ask` | `{question, filters, use_llm = true, route_with_llm = false}` → resposta **determinística na hora** (meta < 1,5 s): `{answer, insights, metrics, chart, table, recommendations, filters, understood, interpretable, narration, facts, meta}` |
| POST | `/api/ai/narrate` | `{question, lang, filters, answer: {answer, insights, recommendations, facts}}` → reescrita da resposta pela IA local, em segundo plano, com trava de fundamentação |
| GET | `/api/ai/status[?refresh=true]` | disponibilidade do Ollama, endereço configurado, modelo em uso e aquecimento |
| GET | `/api/ai/suggestions?lang=pt\|en` | perguntas de exemplo (a interface usa `pt`) |
| GET | `/api/semantic/catalog` | métricas e dimensões governadas |

* `question` aceita perguntas livres em português (ou inglês); apenas os primeiros 500 caracteres são
  considerados; pergunta vazia → 400.
* `narration: {available, model, reason}` diz se vale chamar `/api/ai/narrate` para aquela resposta (rankings,
  listas e what-if não são reescritos); `facts` é o resumo compacto (≤ 1.800 caracteres) que a página devolve
  ao `/api/ai/narrate`.
* `understood: false` + `interpretable: true`: as regras não entenderam a pergunta, mas a IA local está
  disponível. A página repete a pergunta com `route_with_llm: true`; o LLM sugere a intenção, que é validada antes
  de qualquer cálculo (`meta.routing` registra modelo, status e tempo).
* `/api/ai/narrate` devolve `{status: ok|rejected|timeout|unavailable|cancelled, reason, model, elapsed_s,
  answer?, insights?, recommendations?, grounding, complete?}`. Fechar a requisição (a página abortou uma
  narração antiga) interrompe a geração no Ollama. Resposta vazia → 400.
* A barra "Pergunte à IA…" e os botões "Perguntar à IA" da jornada abrem `/app/ai?q=...`, que já envia a
  pergunta. Detalhes em [ai_analyst.md](ai_analyst.md).

## Exportações

| Método | Caminho | Descrição |
|---|---|---|
| GET | `/api/export/excel?scenario_id=` | planilha de planejamento |
| GET | `/api/export/executive-excel` | Excel executivo |
| GET | `/api/export/executive-html[?download=true]` | relatório executivo em HTML autocontido. Renderiza o **mesmo relatório de 7 capítulos** de `/api/story` (ideia central, SCQA, títulos, leituras e a tabela de cada visual), com o rodapé de rastreabilidade e a assinatura. Aceita os filtros do escopo; `download=true` devolve como anexo |

## O que a API não expõe

Não existe endpoint de configurações: a antiga tela de Configurações foi removida e nenhuma resposta inclui caminhos
de arquivos locais (como o caminho do banco DuckDB) nem segredos. O único endereço exposto é o do Ollama, no status
da IA, para indicar se o LLM local está disponível.
