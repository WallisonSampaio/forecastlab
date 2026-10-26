# Modelo de dados

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Formato do arquivo carregado

Colunas mínimas: `Date, Region, Channel, Customer, SKU, Units`.
Opcionais: `CustomerLocation, CustomerPotential, Product, Category, Brand, Revenue, Price, Promotion, Distribution,
StockOut, Holiday, MarketingInvestment, MerchandisingEvent`.

* Os nomes das colunas são reconhecidos sem diferenciar maiúsculas/minúsculas nem acentos, com sinônimos em PT e EN
  (ex.: `Data`, `Região`, `Canal`, `Cliente`, `Produto`, `Quantidade` / `Unidades`, `Receita` / `Faturamento`,
  `Preço`, `Promoção`, `Distribuição`, `Ruptura`, `Feriado`).
* Qualquer dia do mês é aceito; as linhas são agregadas em **Cliente × SKU × Mês**.
* Em arquivos Excel, os dados de vendas são lidos da aba `Dados` (ou `Data` / `Sales`); se ela não existir, vale a
  primeira aba.
* Em arquivos Excel, uma aba cujo nome comece com `Plan` (ex.: `Plano`), `Budget` ou `Orcamento` (sem cedilha),
  com as colunas `Date, Customer, SKU, BudgetUnits, TargetUnits[, BudgetRevenue, TargetRevenue]`, é usada como
  plano. Sem essa aba, o plano é derivado: orçamento = mesmo mês do ano anterior × 1,05 e meta = orçamento × 1,05.
  Nesse caso a jornada avisa que o orçamento foi "estimado automaticamente" e que os desvios vs orçamento são
  ilustrativos.
* Baixe o modelo de planilha na **Entrada** (etapa 1, "Baixar modelo de planilha (.xlsx)"; `/api/data/template`).
  O modelo traz a aba de vendas e a aba "Plano (opcional)" para orçamento e meta.
* Os valores dos dados (regiões, canais, clientes, categorias…) são exibidos como foram carregados; a base de
  demonstração já vem em português.

## Regras de validação (Diagnóstico da base)

| Severidade | Verificações |
|---|---|
| Crítico (bloqueia o forecast) | colunas obrigatórias ausentes, arquivo vazio, datas inválidas, Data/Cliente/SKU/Região/Canal em branco, unidades negativas ou não numéricas, menos de 6 meses de histórico |
| Atenção | linhas duplicadas, datas futuras, unidades em branco (≤ 20%), receita/preço/marketing negativos, distribuição fora de 0–100, outliers (z robusto > 3,5), séries curtas (< 12 meses) |
| Info | linhas agregadas por mês, períodos com demanda zero, colunas opcionais ausentes |

**Score de qualidade dos dados** (0–100) = 35% Completude + 30% Consistência + 20% Profundidade do histórico
(mediana de meses / 48) + 15% Granularidade (atributos de hierarquia presentes).

Os códigos das verificações e os status da base (`valid`, `warnings`, `blocked`) continuam em inglês na API e são
exibidos em português na interface ("Válido", "Com alertas", "Bloqueado").

## Tabelas do DuckDB

| Tabela | Granularidade | Colunas principais |
|---|---|---|
| `datasets` | versão da base | `dataset_version`, nome, origem, linhas, séries, período, score de qualidade, status, flag de ativa, JSON da validação |
| `sales` | versão × data × cliente × SKU | todos os campos canônicos |
| `plan` | versão × data × cliente × SKU | orçamento e meta em unidades e receita |
| `historical_overrides` | versão × data × cliente × SKU | planejador, tipo de evento, % de ajuste, comentário |
| `overrides` | ajuste comercial | cliente (nulo = todos), SKU (nulo = todos), mês, tipo de evento, % de uplift, comentário, autor |
| `forecast_runs` | execução | id da execução, datas/horas, versão da base, horizonte, versão do motor, cenário, status, duração, parâmetros, resumo |
| `series_selection` | execução × série | tipo da série, campeão, desafiante, WMAPE, viés, confiança |
| `series_profiles` | execução × série | estatísticas do perfil e justificativa da classificação |
| `model_registry` | execução × série × modelo | versão do modelo, data de treino, métricas, posição no ranking, parâmetros, flags de campeão/desafiante |
| `backtest_results` | execução × série × modelo × mês | fold, origem, passo do horizonte, real, forecast |
| `forecasts` | execução × série × mês × papel | P50 do campeão/desafiante, σ, P10, P90 |
| `scenarios` | cenário | nome, tipo, descrição, JSON de parâmetros |
| `app_state` | chave | base ativa, execução ativa |

Id da série = `"{Customer}|{SKU}"`. Os nomes das tabelas e colunas permanecem em inglês (contrato técnico estável).

## Gerador sintético

`python -m synthetic_data_generator --seed 42` grava em `data/synthetic/`:

| Arquivo | Conteúdo |
|---|---|
| `sales_history.csv/.parquet` | 60 meses × 220 séries, todos os campos do PRD |
| `budget_target_plan.csv` | orçamento e meta: últimos 12 meses do histórico + 12 meses futuros |
| `historical_overrides.csv` | ajustes de planejadores (informados e otimistas) para o FVA |
| `pending_commercial_events.csv` | eventos comerciais futuros que alimentam o consenso |
| `metadata.json` | semente, padrões por SKU, elasticidades verdadeiras, eventos (gabarito para validação) |

Com `--samples ../data/samples` ele também grava `forecastlab_sample_upload.xlsx` (e a versão `.csv`), o recorte
das regiões **Sul** e **Centro-Oeste**, pronto para ser carregado como exemplo na **Entrada** (etapa 1).

Os valores de negócio são gerados em português:

| Campo | Valores |
|---|---|
| Região | Sudeste, Sul, Nordeste, Centro-Oeste, Norte |
| Canal | Varejo Moderno, Atacarejo, Varejo Tradicional, E-commerce, Farma |
| Categoria | Bebidas, Snacks, Cuidados Pessoais, Limpeza |
| Tipo de evento | Promoção, Merchandising, Ganho de distribuição, Perda de distribuição, Nova loja, Ganho de cliente, Perda de cliente, Campanha, Mudança de preço, Lançamento, Deslistagem, Ação de concorrente |
| Planejador | Key Account (KAM), Diretor de Vendas, Trade Marketing, Planejador de Demanda, Marketing |

Demanda = nível × tendência × sazonalidade × eventos de calendário × abertura de lojas × distribuição^0,9 ×
preço relativo^ε × promoção × merchandising × marketing^0,07 × quebras estruturais × ruído × (1 − perda por
ruptura).
