# Metodologia de forecast

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## 1. Montagem do painel

* Granularidade: **Cliente × SKU × Mês** (arquivos com dados diários ou semanais são agregados por mês).
* Cada série vai do seu primeiro registro até o fim da base; meses sem registro são considerados demanda zero.
* Calendário por mês: índice de tempo `t`, `mês`, feriados brasileiros (Carnaval e Páscoa calculados ano a ano).
* Drivers, quando disponíveis: promoção, preço, distribuição, merchandising, investimento em marketing.

## 2. Perfil e classificação das séries

| Estatística | Definição |
|---|---|
| média, mediana, variância, CV | estatísticas descritivas |
| % de demanda zero | proporção de meses com demanda zero |
| ADI / CV² | intervalo médio entre demandas e CV² da demanda não nula (Syntetos–Boylan) |
| força da tendência | `max(0, 1 − Var(R)/Var(T+R))` a partir de STL robusto |
| força da sazonalidade | `max(0, 1 − Var(R)/Var(S+R))` a partir de STL robusto |
| quebra estrutural | melhor ponto de mudança único (média em dois segmentos) vs. SSE da tendência linear |
| lift / correlação de promoção | demanda vs. mediana móvel em meses com e sem promoção |
| correlação com distribuição | demanda dessazonalizada vs. distribuição numérica |

Ordem de classificação (vale a primeira regra atendida): Inativa → Histórico curto → Intermitente → Dirigida por
distribuição → Mudança estrutural → Sazonal → Dirigida por promoção → Crescente / Em declínio → Volátil → Estável.
Cada série guarda a justificativa em linguagem simples (ex.: *"ADI 2,10 ≥ 1,32 (52% de meses zerados)"*).

> Os códigos internos (`Stable`, `Seasonal`, `Intermittent`…) permanecem em inglês na API e são exibidos em
> português na interface.

## 3. Catálogo de modelos (15 modelos)

| Família | Modelos |
|---|---|
| Linha de base | Naive, Naive Sazonal, Média Móvel (3) |
| Suavização exponencial | SES, Holt (amortecido), Holt-Winters (amortecido, sazonalidade aditiva/multiplicativa), ETS (automático por AICc) |
| ARIMA | ARIMA(1,1,1) com drift quando significativo, SARIMA(0,1,1)(0,1,1)₁₂ em escala log |
| Demanda intermitente | Croston, SBA (corrigido de viés), TSB (trata obsolescência) |
| Regressão | Ridge sobre a demanda em log: tendência, sazonalidade mensal, promoção, log do preço, log da distribuição, merchandising, log do marketing, feriados (retransformação por smearing) |
| Machine Learning | Random Forest, Gradient Boosting (scikit-learn) com lag-12, calendário e drivers (recursivo além de 12 passos) |

Todos os modelos compartilham uma interface sem estado: `forecast(y_train, h, X_train, X_future) → mean, params`.

## 4. Roteador de modelos candidatos

| Tipo de série | Candidatos (o Naive sempre participa) |
|---|---|
| Intermitente | Croston, SBA, TSB, Média Móvel |
| Sazonal | Naive Sazonal, Holt-Winters, ETS, SARIMA, Regressão |
| Crescente / Em declínio | Holt, ETS, ARIMA, Regressão, Naive Sazonal |
| Dirigida por promoção | Regressão, Random Forest, Gradient Boosting, ETS, Naive Sazonal |
| Dirigida por distribuição | Regressão, Gradient Boosting, Holt, ETS |
| Mudança estrutural | SES, Holt, ETS, ARIMA, Média Móvel |
| Volátil | Média Móvel, SES, ETS, Random Forest, Gradient Boosting, Naive Sazonal |
| Estável | SES, Média Móvel, ETS, ARIMA, Regressão, Naive Sazonal |
| Histórico curto | Média Móvel, SES, Holt, ETS |

O roteador pode ser desligado em cada execução ("rodar os 15 modelos").

## 5. Backtest rolling-origin

* Janela expansível; padrão de **4 folds × 3 meses** → os últimos 12 meses são previstos fora da amostra.
* Folds com menos de 12 meses de treino são ignorados; modelos que exigem mais histórico são marcados como
  `insufficient_history`.
* **Sem vazamento de dados**: o treino usa apenas `y[:origem]`; os drivers da janela de teste ficam congelados em
  valores de "negócio normal" calculados na janela de treino (preço regular, última distribuição, marketing
  mediano, intensidade promocional usual); a limpeza de rupturas usa só os meses de treino. Testes:
  `backend/tests/test_backtest.py`.

## 6. Métricas

| Métrica | Fórmula |
|---|---|
| MAE | média(\|F − A\|) |
| RMSE | √média((F − A)²) |
| MAPE | média(\|F − A\| / A), A ≠ 0 |
| sMAPE | média(2\|F − A\| / (\|A\| + \|F\|)) |
| **WMAPE** (principal) | Σ\|F − A\| / Σ\|A\| |
| MASE | MAE / MAE do naive sazonal dentro da amostra |
| Viés | Σ(F − A) / ΣA (positivo = superestimado) |
| Acurácia do forecast | max(0, 1 − WMAPE) |

*F = forecast, A = real.*

Classes de viés: 🔵 Subestimado (< −5%) · 🟢 Equilibrado · 🔴 Superestimado (> +5%).

## 7. Campeão, Desafiante e confiança

Ranking: WMAPE → |Viés| → RMSE. 1º lugar = **Campeão**, 2º lugar = **Desafiante**.

Score de confiança (0–100): erro (≤ 15% → 40 pts), estabilidade entre folds (desvio-padrão do WMAPE por fold),
profundidade do histórico (≥ 48 meses) e margem do campeão sobre o desafiante. ≥ 75 Alta · ≥ 50 Média · abaixo
disso, Baixa.

## 8. Forecast e intervalos de previsão

* Treino final em todo o histórico (com rupturas tratadas); horizonte padrão de 12 meses (3/6/12/18/24
  disponíveis).
* σ₁ = RMSE dos erros fora da amostra do backtest do campeão; σₕ = σ₁·√(h / h̄).
* P50 = forecast do modelo; P10/P90 = P50 ∓ 1,2816·σₕ (P10 limitado a 0).
* Agregação entre séries/meses: `σ = √((1−ρ)Σσᵢ² + ρ(Σσᵢ)²)` com ρ = 0,3.

## 9. Hierarquia e reconciliação

Empresa → Região → Canal → Cliente → Categoria → SKU. Bottom-up por padrão (cada nível é a soma exata dos forecasts
Cliente × SKU); top-down por proporções históricas está disponível na API (`/api/forecast/hierarchy?method=top_down`);
MinT / middle-out estão previstos na interface do reconciliador para uma próxima versão. Na interface, a navegação
pela hierarquia acontece no deep dive dos desvios (Região → Canal → Cliente → Categoria → SKU → Série).

## 10. Registros e versionamento

* **Registro de modelos**: SeriesID, Modelo, Versão do modelo, data de treino, corte dos dados, WMAPE, Viés, MAE,
  RMSE, MASE, WMAPE por fold, posição no ranking, parâmetros (JSON), indicadores de Campeão/Desafiante.
* **Registro de execuções**: RunID, data/hora, versão da base, horizonte, versão do motor, cenário, status,
  duração, séries e modelos avaliados, parâmetros e resumo da execução.
* **Versionamento de bases**: cada arquivo carregado → `dataset_YYYY_MM_vNN`.

## Desempenho

220 séries × ~6 modelos roteados × 5 treinos (4 folds + treino final) ≈ 6.600 treinos de modelo por execução,
processados em paralelo por processos de trabalho (workers), em ≈ 2–5 minutos em um notebook. Desligue o roteador
apenas para demonstrações.
