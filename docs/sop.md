# S&OP: relatório executivo, deep dive dos desvios, metas e FVA

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

O antigo cockpit de S&OP (8 KPIs, tabela trimestral, tabelas de viabilidade, riscos e oportunidades) deu lugar a
duas etapas da jornada guiada (veja [jornada.md](jornada.md)):

* o **Relatório executivo** (`/app/relatorio/:capitulo`) conta a mensagem da reunião em 7 capítulos, cada um com
  um título que afirma a conclusão, um único visual e até 3 leituras;
* o **Deep dive dos desvios** (`/app/desvios`) explica onde, por quê e quando o número desviou do orçamento, da
  meta ou do realizado, e leva à ação.

O endpoint `/api/sop/cockpit` continua existindo e é a referência numérica: o consenso do capítulo "Próximos
meses" e o desvio do deep dive são iguais aos dele (verificado por teste).

## Relatório executivo

Todos os capítulos vêm de um único `GET /api/story` e usam as mesmas funções do deep dive (`deviations.service`),
da confiança (`services/trust.py`) e da viabilidade (`sop.feasibility.assess`). Os números de cada título ficam em
`facts`, e um teste confere que o texto formatado é igual ao número. Regras de texto: no máximo 3 números por
título, até 220 caracteres, nenhum "—" no lugar de um dado ausente (o capítulo vira `empty` com um aviso).

| # | Capítulo | Comparação e período | Visual | Abre o deep dive em |
|---|---|---|---|---|
| 1 | Resumo | todas | 4 KPIs + SCQA + o roteiro | `cmp=fc_pl`, horizonte, por cliente |
| 2 | Realizado | Real × Orçamento, últimos 12 meses | ponte Orçamento → Volume → Mix → Preço → Real | `cmp=ac_pl`, `u12m`, por cliente |
| 3 | Precisão | Real × Estatístico, janela de backtest | erro por causa | `cmp=ac_fc`, `bt`, por cliente |
| 4 | Próximos {h} meses | Consenso × Orçamento, horizonte | colunas mensais de variação, com trimestres | `cmp=fc_pl`, horizonte, por região |
| 5 | Gap vs orçamento | Consenso × Orçamento, horizonte | barras de variação por cliente (top 8 + Demais) | `cmp=fc_pl`, por cliente, com o 1º cliente em foco |
| 6 | Meta | Consenso × Meta, horizonte | faixa de viabilidade P10–P90 | `cmp=fc_tg`, horizonte, por região |
| 7 | Decisões | regras D1–D8 | tabela de até 5 decisões | `cmp=fc_pl`, por série |

### 1 · Resumo

A **ideia central** (Pirâmide de Minto) muda conforme o caso:

| Caso | Modelo do texto |
|---|---|
| consenso > 0,5% abaixo do orçamento | "Vamos {crescer X%} nos próximos {h} meses, mas fechar {gap} abaixo do orçamento: {n} clientes concentram {share} das perdas e a meta tem {prob} de chance." |
| alinhado (±0,5%) | "O consenso dos próximos {h} meses está alinhado ao orçamento e a meta tem {prob} de chance ({classe})." |
| acima do orçamento | "Vamos {crescer X%} e superar o orçamento em {gap}; a meta tem {prob} de chance — o foco é garantir abastecimento para o upside." |
| base sem orçamento | "Vamos {crescer X%} nos próximos {h} meses (consenso de {fc}); esta base não tem orçamento nem meta para comparar." |

Abaixo, o **SCQA** em três linhas (Situação: como fechamos os últimos 12 meses; Complicação: consenso vs
orçamento e meta; Resposta: as decisões do capítulo 7), 4 KPIs (Real · últimos 12 meses, Consenso · próximos
{h} meses, Chance de bater a meta, Acurácia do forecast) e "O roteiro": os títulos dos capítulos 2–7, cada um
clicável.

### 2 · Realizado

Usa a ponte preço/volume/mix do realizado (fórmulas abaixo). Quando o volume foi positivo e a receita negativa, o
título diz isso: *"Vendemos 4,0% mais unidades que o orçado, mas a receita ficou 3,9% abaixo do orçamento (R$ 3,58
mi): preço (-R$ 5,00 mi) e mix (-R$ 2,26 mi) anularam o ganho de volume."* As leituras trazem o crescimento sobre o
ano anterior e o atingimento do orçamento e da meta; a parte do efeito preço vinda de meses com promoção e o
preço realizado nos meses regulares (índice de Paasche); e o cliente que mais perdeu vs orçamento.

### 3 · Precisão

Erro fora da amostra (backtest com origem móvel), WMAPE em unidades, impacto valorizado ao preço realizado. O
título destaca a parte **controlável** do erro quando ela passa de 30% (*"…45% do erro tem causa controlável:
promoção não antecipada lidera (19%)"*); caso contrário, a parte inerente, com a recomendação de gerir com estoque
de segurança. Se o forecast não superou o método ingênuo, o título começa com "Atenção". Leituras: viés e parte
sistemática do erro; FVA dos ajustes comerciais e o pior tipo de evento (mínimo de 10 ajustes); os clientes que
concentram o erro.

### 4 · Próximos meses

*"O consenso projeta R$ 94,30 mi até set/2027 (+7,3% vs últimos 12 meses): R$ 4,09 mi abaixo do orçamento e R$
11,70 mi abaixo da meta."* Leituras:

1. o trimestre mais crítico e o pior mês ("T1 · out–dez/2026 é o trimestre mais crítico (-R$ 1,65 mi); dez/2026
   sozinho responde por -R$ 1,34 mi");
2. onde o orçamento e a meta caem em relação à **faixa provável P10–P90 do consenso** (dentro, acima ou abaixo);
3. o total dos eventos comerciais cadastrados no horizonte (ou "o consenso é igual ao estatístico").

Sem orçamento, a referência do gráfico passa a ser o ano anterior.

### 5 · Gap vs orçamento

O nível é o primeiro entre Cliente → Categoria → SKU que o escopo não fixou e que tem pelo menos 2 membros. O
título nomeia quem concentra as perdas (Pareto, até 3 membros) e mostra se o problema é **premissa** (o orçamento
supõe um crescimento muito acima do que o forecast indica) ou outro fator (rótulo da causa principal). Leituras:

1. a ponte em uma frase: volume, mix, preço e eventos, e o prêmio de preço que o orçamento assume vs o preço atual;
2. o upside: quantos membros estão acima do orçamento e quem lidera;
3. a chance de o principal membro atingir o orçamento e se o desvio é **recorrente** (já ficou ≥ 5% abaixo do
   orçamento nos últimos 12 meses — "desvio recorrente, não ruído").

### 6 · Meta

O título segue a classe de viabilidade da meta:

| Classe | Modelo do texto |
|---|---|
| Desafiadora | "A meta de {meta} é desafiadora: {prob} de chance — fechar {gap} exige {alavanca}." |
| Agressiva | "A meta de {meta} é improvável ({prob}): exige {crescimento exigido} de crescimento contra {previsto} previstos — recalibre ou comprometa alavancas concretas." |
| Realista | "A meta de {meta} é realista ({prob} de chance): proteja a base — disponibilidade e execução." |
| Subestimada | "A meta de {meta} está abaixo do resultado provável ({prob} de chance) — há espaço para elevá-la." |

**Alavanca:** entre as alavancas plausíveis do motor de viabilidade, a de **menor esforço normalizado**
(|mudança exigida| ÷ limite plausível: distribuição 20%, marketing 50%, promoções = meses do horizonte ÷ 3).
Preço fica de fora: cortar preço não é alavanca de receita. Sem alavanca plausível, o texto diz "mais de uma
alavanca combinada". O botão "Simular alavanca" abre Cenários e metas com a alavanca já preenchida (ex.:
`/app/scenarios?distribution_change_pct=0.133`). Leituras: a posição da meta na faixa P10–P90; crescimento exigido
× previsto × histórico; a região com menor chance e quantas regiões têm meta agressiva.

### 7 · Decisões

Regras determinísticas — nenhum número é gerado por IA. Todas as regras são avaliadas, ordenadas pelo impacto, no
máximo uma por código, e as **5 maiores** entram na tabela. Os impactos **nunca são somados** (o gap da meta contém
parte do gap do orçamento). Impactos medidos na janela de backtest são anualizados para o horizonte
(× h ÷ meses do backtest), para ordenar tudo na mesma escala.

| Código | Quando dispara | Decisão | Impacto | Dono |
|---|---|---|---|---|
| D1 | clientes com tag "Premissa de crescimento otimista" somam \|desvio\| ≥ 1% do orçamento | Revisar o orçamento de {clientes} | \|Σ desvio\| no horizonte | Key Account + FP&A |
| D2 | promoção + merchandising não antecipados ≥ 15% do erro | Cadastrar o calendário promocional como ajuste comercial antes do consenso | erro dessas causas, anualizado | Trade Marketing + Demanda |
| D3 | clientes acima do orçamento somam ≥ 0,5% do orçamento | Garantir abastecimento para o upside de {clientes} | Σ desvios positivos | Supply + Key Account |
| D4 | meta Desafiadora ou Agressiva | Decidir: recalibrar a meta ou aprovar {alavanca} | gap vs meta | Diretoria Comercial |
| D5 | séries com \|sinal de rastreamento\| ≥ 4,5 ou \|viés\| ≥ 15% | Corrigir o viés de {n} séries | Σ WMAPE × receita prevista das séries | Planejamento de Demanda |
| D6 | tipo de evento com FVA ≤ -2 p.p. em ≥ 10 ajustes | Rever a regra de ajustes de {tipo} | erro adicionado pelos ajustes, anualizado | Planejamento + Comercial |
| D7 | efeito preço negativo ≥ 1% do orçamento | Revisar a premissa de preço do orçamento | \|efeito preço\| | FP&A + Pricing |
| D8 | meta Subestimada | Elevar a meta: o consenso já a supera | \|gap vs meta\| | Diretoria Comercial |

Na base de demonstração: D4 (R$ 11,70 mi), D5 (R$ 5,50 mi, 68 séries), D2 (R$ 3,84 mi), D1 (R$ 2,96 mi, Litoral
Market e Rede Horizonte Supermercados) e D3 (R$ 886,9 mil).

### Exportação

"Baixar relatório (HTML)" (`/api/export/executive-html?download=true`) gera um arquivo autocontido com a ideia
central, o SCQA e os 7 capítulos — os mesmos títulos da tela, as leituras e a tabela de cada visual —, a linha de
rastreabilidade (base, execução, origem do orçamento, antecedência do backtest) e a assinatura.

## Deep dive dos desvios

### Lentes, comparações e períodos

| Lente | Comparação (`cmp`) | Período padrão | Outros períodos |
|---|---|---|---|
| Plano | Consenso × Orçamento (`fc_pl`) | próximos {h} meses | trimestres T1–T4, cada mês do horizonte |
| Plano | Consenso × Meta (`fc_tg`) | próximos {h} meses | idem |
| Plano | Real × Orçamento (`ac_pl`) | últimos 12 meses | cada mês |
| Previsão | Real × Estatístico, campeão (`ac_fc`) | janela de backtest | cada mês do backtest |
| Previsão | Real × Consenso histórico, com ajustes (`ac_cs`) | janela de backtest | idem |

Na lente Plano, a medida pode ser receita ou unidades; na lente Previsão, o WMAPE é sempre em unidades e o impacto
em R$ ao preço realizado. A lente Previsão também agrupa por **modelo campeão** e por **padrão de demanda**.
Comparações sem dados ficam desabilitadas com o motivo ("— sem orçamento nesta base", "— sem histórico de
ajustes").

### KPIs (sempre 4, montados no backend)

| Comparação | KPI 1 | KPI 2 | KPI 3 | KPI 4 |
|---|---|---|---|---|
| Consenso × Orçamento | Desvio vs orçamento (R$ e %) | Chance de atingir o orçamento (com a faixa P10–P90) | Concentração ("1 de 5 regiões", "55% das perdas") | Principal fator (o maior efeito na direção do desvio) |
| Consenso × Meta | Desvio vs meta | Chance de bater a meta (com a classe) | Concentração | Principal fator (pode ser "Desafio comercial" = meta − orçamento) |
| Real × Orçamento | Desvio vs orçamento (U12M) | Atingimento do orçamento | Concentração | Principal fator |
| Real × Estatístico | Acurácia (WMAPE em unidades) | Viés (positivo = superestimou) | Erro absoluto (R$, % sistemático) | Causa principal (% do erro) |
| Real × Consenso | Acurácia do consenso | Viés | Erro absoluto | Valor dos ajustes (FVA, p.p.) |

### Títulos e diagnóstico

O título do deep dive é gerado para o recorte atual. Exemplos da base de demonstração:

* Plano, empresa toda: *"Empresa toda: consenso R$ 4,09 mi abaixo do orçamento (-4,2%) nos próximos 12 meses —
  Nordeste responde por 55% das perdas."*
* Plano, cliente em foco: *"Litoral Market: R$ 1,58 mi abaixo do orçamento (-22,0%); causa principal: premissa de
  crescimento otimista — já ficou -17,2% vs orçamento nos últimos 12 meses."*
* Previsão, empresa toda: *"Empresa toda: o forecast estatístico errou 14,8% (R$ 15,40 mi) na janela de backtest
  (out/2025–set/2026); demanda intermitente ou volátil explica 27% e o viés é de -3,3% (equilibrado)."*

Abaixo de "Por que desviou?", o **Diagnóstico** traz até 3 frases, cada uma só quando a condição vale:

| Lente | Condição | Frase |
|---|---|---|
| Plano | desvio recorrente (fc_*) | "O desvio é recorrente: nos últimos 12 meses {membro} já ficou {x%} vs orçamento." |
| Plano | sempre que houver ano anterior | "O orçamento supõe {g_plano} de crescimento sobre o ano anterior; o forecast indica {g_fc}." (Consenso × Meta: "A meta supõe…"; Real × Orçamento: "O orçamento supunha… o realizado foi…") |
| Plano | \|efeito preço\| ≥ 25% do desvio | futuro: prêmio de preço do orçamento vs o praticado; realizado: preço nos meses regulares e parte do efeito vinda de promoções |
| Plano | Real × Orçamento com backtest | "Do efeito volume ({vol}), {antecipado} já estava no forecast {1–3 meses} antes e {surpresa} foi surpresa de demanda." |
| Plano | eventos ≠ 0 | "Eventos comerciais somam {valor} ({n} ajustes; maior: {tipo})." |
| Previsão | sempre | "{x%} do erro é viés sistemático; o restante é ruído que se compensa." |
| Previsão | causa principal | "{causa}: {valor} de erro em {n} meses-série, quase sempre subestimando / superestimando" (ou "com erros nos dois sentidos") |
| Previsão | causa principal inerente e uma causa controlável ≥ 5% do erro | "Entre as causas controláveis, {causa} lidera: {valor} ({x%} do erro)." — os botões de ação passam a apontar para essa causa |
| Previsão | consenso com ajustes | "Ajustes comerciais: {x p.p.} de ganho de acurácia." |

### Exceções ("Quais séries tratar primeiro?")

| Lente | Critério (todas as condições) | Ordem |
|---|---|---|
| Plano | \|desvio\| ≥ max(R$ 10 mil ou 1.000 un.; 0,1% do orçamento do recorte) **e** (\|desvio %\| ≥ 5% **ou** probabilidade de o desvio se confirmar ≥ 70%) **e** tag principal ≠ "Dentro da incerteza" | \|desvio\| × probabilidade (futuro) ou \|desvio\| (realizado) |
| Previsão | qualquer uma: WMAPE ≥ 35% (séries com ≥ 0,1% da receita prevista), \|viés\| ≥ 15%, \|sinal de rastreamento\| ≥ 4,5 | erro absoluto em R$ |

As linhas da quebra ("Onde está o desvio?") são marcadas como exceção com o mesmo critério, mas com materialidade
de 1% do orçamento do recorte.

## Definições e fórmulas

### Grão, preços e grade completa

* **Célula** = série Cliente × SKU × mês.
* **Preço do forecast** = mediana do preço regular dos últimos 6 meses da série. **Preço realizado** da célula =
  receita ÷ unidades. **Preço do orçamento** da célula = receita orçada ÷ unidades orçadas.
* As células formam a **grade completa** séries × meses: orçamento sem venda conta como venda zero, e venda sem
  orçamento conta como orçamento zero. (Um *left join* a partir do realizado perde 19 células orçadas na base de
  demonstração e muda o desvio dos últimos 12 meses de -R$ 3,58 mi para -R$ 3,40 mi.)

### Ponte preço / volume / mix / eventos

Exata e aditiva em qualquer partição das células. Seja P̄ o preço médio orçado do recorte (Σ receita orçada ÷ Σ
unidades orçadas).

| Efeito | Fórmula por célula |
|---|---|
| Volume | (Q_comparado − Q_orçado) × P̄ |
| Mix | (Q_comparado − Q_orçado) × (preço orçado da célula − P̄) + resíduo |
| Preço | Q_comparado × (preço comparado − preço orçado da célula) |
| Eventos | unidades incrementais dos ajustes comerciais × preço (só no futuro) |
| Identidade | Volume + Mix + Preço + Eventos = Receita comparada − Receita orçada (testado a 1e-6) |

* Q_comparado = forecast estatístico (P50) no futuro e unidades reais no realizado; os eventos ficam à parte.
* Consenso × Meta: Meta → Desafio comercial (meta − orçamento) → Orçamento (subtotal) → efeitos → Consenso.
* Em **unidades** não há preço nem mix: Orçamento → Volume → Eventos → Consenso.
* Ao detalhar um membro, a ponte usa o P̄ do próprio membro: o desvio não muda, mas a divisão entre volume e mix
  pode mudar. Nota do gráfico: "Volume valorizado ao preço médio orçado do recorte; mix no nível Cliente × SKU ×
  mês."

**Direcionadores**

| Direcionador | Definição | Onde |
|---|---|---|
| Efeito preço em meses com promoção | Σ efeito preço das células com promoção | realizado |
| Preço realizado nos meses regulares | índice de **Paasche** sem mix: Σ Q_real·p_real ÷ Σ Q_real·p_orçado − 1, nas células sem promoção com orçamento e venda (-3,6% na demonstração; a razão de preços médios daria -5,5%, porque mistura preço com mix) | realizado |
| Prêmio de preço do orçamento | preço médio orçado ÷ preço atual aplicado às unidades orçadas − 1 (+0,8% na demonstração) | futuro |
| Eventos por tipo | Σ efeito eventos por tipo de ajuste comercial (sobreposições divididas pela participação no uplift) | futuro |
| Volume antecipado × surpresa | antecipado = Σ (forecast do backtest − orçado) × P̄; surpresa = Σ (real − forecast do backtest) × P̄; sem cobertura = Σ (real − orçado) × P̄ nas células sem backtest. O preço nunca é atribuído ao forecast | realizado |

### Probabilidade de atingir a referência

Para o horizonte: σ do recorte = σ agregado das células (√((1−ρ)Σσᵢ² + ρ(Σσᵢ)²), ρ = 0,3), escalado para o
consenso; chance de atingir = 1 − Φ((referência − consenso) ÷ σ). Na empresa toda, para a meta, o valor é
idêntico ao do motor de viabilidade (testado). A **faixa P10–P90** da jornada é sempre a do consenso
(consenso ∓ 1,2816·σ).

### Pareto e concentração

Membros adversos ordenados do maior para o menor desvio; **n_top** = menor k com participação acumulada ≥ 50%,
limitado a 1–3 ("2 de 14 clientes concentram 59% das perdas"). Com desvio positivo, o cálculo usa os membros
favoráveis ("do ganho"). A quebra mostra os 12 membros de maior |desvio| (perdas primeiro, depois ganhos) e soma
o resto em "Demais (n)".

### Erro de previsão

Fonte: `backtest_results` do campeão de cada série (fora da amostra, drivers congelados na origem).

| Métrica | Definição |
|---|---|
| WMAPE | Σ\|forecast − real\| ÷ Σ real, em unidades |
| Viés | Σ(forecast − real) ÷ Σ real (positivo = superestimou) |
| Erro absoluto (R$) | Σ \|erro em unidades\| × preço realizado da célula |
| Sistemático × ruído | sistemático = Σ por série de \|Σ erro em R$\|; ruído = erro absoluto − sistemático (o que se compensa ao longo dos meses) |
| Sinal de rastreamento | Σ erro das últimas 6 células ÷ erro absoluto médio dessas células (\|TS\| ≥ 4,5 = viés persistente) |
| Ingênuo | WMAPE do modelo ingênuo nas mesmas células (mesma regra do FVA) |
| Consenso histórico | forecast estatístico × (1 + Σ ajustes históricos da célula), limitado a zero |

## Causa raiz

### Tags do plano

Avaliadas em ordem; cada membro ou série recebe no máximo 2 tags, e a primeira é a principal.

| # | Tag | Regra |
|---|---|---|
| 1 | Meta acima do orçamento | Consenso × Meta, desvio negativo e (meta − orçamento) ≥ 50% do desvio |
| 2 | Sem orçamento | orçamento zero com venda/forecast positivo |
| 3 | Premissa de crescimento otimista | desvio negativo e crescimento orçado − crescimento previsto ≥ 8 p.p. |
| 4 | Crescimento não orçado | desvio positivo e crescimento previsto − crescimento orçado ≥ 8 p.p. |
| 5 | Queda estrutural | desvio negativo e (≥ 30% da receita em séries em declínio/mudança estrutural/inativas, ou ajuste de perda de cliente, perda de distribuição ou deslistagem) |
| 6 | Preço abaixo/acima do orçado | \|efeito preço\| ≥ 40% do desvio, mesmo sinal |
| 7 | Mix desfavorável/favorável | \|efeito mix\| ≥ 40% do desvio, mesmo sinal |
| 8 | Eventos comerciais | \|efeito eventos\| ≥ 40% do desvio, mesmo sinal |
| 9 | Dentro da incerteza | futuro, chance entre 35% e 65% e \|desvio %\| < 5% |
| 10 | Volume abaixo/acima do orçado | caso contrário |

### Causa do erro de previsão

Cada mês-série recebe **exatamente uma** causa, pela ordem de prioridade, e só quando o sinal do erro (forecast −
real) é coerente com ela. Exemplo: um mês de promoção em que o forecast **superestimou** não é "Promoção não
antecipada" — sem essa trava, o rótulo daria uma explicação falsa.

| # | Causa | Grupo | Regra |
|---|---|---|---|
| 1 | Ajuste comercial piorou o forecast | Controlável | consenso histórico com ajuste e erro maior que o do estatístico (+0,5% do real) |
| 2 | Ruptura de estoque | Controlável | ruptura no mês e forecast acima do real |
| 3 | Promoção não antecipada | Controlável | promoção no mês e forecast abaixo do real (no consenso: sem ajuste registrado) |
| 4 | Merchandising não antecipado | Controlável | merchandising no mês e forecast abaixo do real |
| 5 | Mudança de distribuição | Controlável | distribuição mudou ≥ 5 p.p. desde a origem, erro no sentido oposto |
| 6 | Mudança de preço | Controlável | sem promoção, preço ≥ 5% diferente do preço de referência da origem, erro no mesmo sentido |
| 7 | Mudança de patamar | Controlável | quebra estrutural nos 12 meses anteriores ou \|sinal de rastreamento\| ≥ 4,5 |
| 8 | Demanda intermitente ou volátil | Inerente | série intermitente, volátil, de histórico curto ou inativa |
| 9 | Variação normal (dentro da faixa P10–P90) | Inerente | \|erro\| ≤ 1,2816 × RMSE da série |
| 10 | Sem causa identificada | Sem causa | caso contrário |

Na base de demonstração, cerca de 45% do erro tem causa controlável (promoção não antecipada lidera, com 19%) e a
maior causa isolada é inerente (demanda intermitente ou volátil, 27%).

### Ações recomendadas

| Tag ou causa | Ação recomendada | Botão principal |
|---|---|---|
| Premissa de crescimento otimista | Revisar a premissa de crescimento do orçamento com o Key Account e o FP&A. | Perguntar à IA · Simular cenário |
| Crescimento não orçado | Garantir abastecimento para o upside e avaliar elevar a meta. | Simular cenário |
| Preço (plano) | Validar a política de preço orçada com Pricing/FP&A. | Perguntar à IA |
| Mix | Revisar mix e sortimento com Trade Marketing. | Perguntar à IA |
| Eventos comerciais | Confirmar os eventos comerciais com o time da conta. | Abrir ficha |
| Queda estrutural | Plano de recuperação ou ajuste do orçamento. | Criar ajuste comercial (Perda de distribuição, -10%) |
| Meta acima do orçamento | Decidir: recalibrar a meta ou comprometer alavancas. | Simular cenário |
| Promoção / Merchandising | Cadastrar a promoção (ou ação de merchandising) de {mês} como ajuste comercial. | Criar ajuste comercial, pré-preenchido: mesmo mês do ano seguinte (se estiver no horizonte; senão o 1º mês), uplift = lift de promoção da série limitado a 5%–50% (sem lift medido: padrão da biblioteca, 25% ou 12%) |
| Ruptura | Erro causado por ruptura: tratar abastecimento e estoque de segurança — não é falha do modelo. | Abrir ficha |
| Mudança de distribuição | Atualizar a premissa de distribuição e simular. | Simular cenário |
| Mudança de preço (previsão) | Alinhar a política de preço com o planejamento de demanda. | Perguntar à IA |
| Mudança de patamar | Viés persistente: encurtar a janela de treino, registrar a mudança de patamar ou promover o desafiante. | Abrir no workspace |
| Ajuste piorou o forecast | Revisar a regra de ajustes manuais (FVA negativo). | Ver valor dos ajustes (FVA) |
| Demanda intermitente ou volátil | Gerir com estoque de segurança, não com precisão de ponto. | — |
| Variação normal, incerteza, volume, sem causa | Monitorar no próximo ciclo. | — |

Os botões "Perguntar à IA" usam perguntas testadas contra o classificador de intenções (veja
[ai_analyst.md](ai_analyst.md)).

## Base vs incremental

```text
Demanda base (P50 estatístico)
+ Demanda incremental (ajustes comerciais: Σ % de uplift × demanda base)
= Forecast de consenso
```

Biblioteca de eventos: Promoção, Merchandising, Ganho de distribuição, Perda de distribuição, Nova loja, Ganho de
cliente, Perda de cliente, Campanha, Mudança de preço, Lançamento, Deslistagem, Ação de concorrente. Um ajuste
comercial pode valer para um SKU em um cliente ou para todos os SKUs de um cliente, em qualquer mês do horizonte. Ele
pode ser criado no Workspace de forecast ou direto na ficha da série do deep dive.

## Motor de Viabilidade de metas — "Esta meta é realista?"

O consenso é tratado como N(consenso, σ), com σ agregado a partir dos erros fora da amostra do backtest.

| Entrada | Uso |
|---|---|
| P(demanda ≥ meta) | classificação principal |
| meta vs P10 / P50 / P90 | posição dentro da faixa plausível |
| crescimento exigido vs ano anterior vs crescimento histórico | teste de ambição |
| potencial do cliente | meta acima do potencial endereçável → Agressiva |
| eventos planejados | incremental já incluído no consenso |
| volatilidade histórica | contexto |

| Classe | Regra |
|---|---|
| Subestimada (`UNDERESTIMATED`) | meta ≤ P10 ou probabilidade ≥ 90% |
| Realista (`REALISTIC`) | probabilidade ≥ 50% |
| Desafiadora (`STRETCH`) | 20% ≤ probabilidade < 50% e meta ≤ P90 |
| Agressiva (`AGGRESSIVE`) | demais casos, ou acima do potencial, ou crescimento exigido muito acima do histórico |

Na interface, cada classe aparece com ícone e rótulo (nunca só com cor).

**Calibração** — crescimento incremental exigido vs orçamento (ex.: orçamento de R$ 10 mi e meta de R$ 11 mi →
+10%), gap vs consenso e a mudança em **uma única alavanca** que fecharia o gap sozinha (distribuição, preço,
marketing ou meses com promoção), marcada como plausível ou irrealista. O capítulo Meta escolhe a alavanca de menor
esforço normalizado, sem preço (veja acima).

## Alocação de metas

Aba "Alocação de metas" em **Cenários e metas**. Distribui uma meta total por região, canal, cliente, categoria ou
SKU:

* **Peso histórico** — participação nos últimos 12 meses
* **Baseado no potencial** — participação no espaço de crescimento (potencial do cliente − volume atual)
* **Baseado no forecast** — participação no forecast de consenso
* **Estratégico** — pesos definidos pelo usuário (grade editável)

Cada meta alocada recebe sua própria classe de viabilidade e probabilidade.

## Forecast Value Added (FVA)

Célula a célula (Cliente × SKU × Mês) nos últimos 12 meses:

```text
Ingênuo  →  Estatístico (campeão, fora da amostra)  →  Consenso (após os ajustes dos planejadores)
FVA = erro(etapa anterior) − erro(etapa atual)
```

Exemplo: estatístico 100, ajuste do planejador para 120, real 103 → **"O ajuste reduziu a acurácia do forecast."**

O FVA aparece em três lugares:

* aba **"Valor dos ajustes (FVA)"** em Modelos e FVA: a escada de valor, o valor agregado por tipo de evento,
  planejador ("Key Account (KAM)", "Diretor de Vendas", "Trade Marketing", "Planejador de Demanda", "Marketing"),
  direção e magnitude (tabela com barras), e o log completo de ajustes;
* capítulo **Precisão** do relatório (ganho dos ajustes e o pior tipo de evento) e decisão **D6**;
* lente **Previsão** do deep dive, comparação Real × Consenso histórico (KPI "Valor dos ajustes (FVA)" e a causa
  "Ajuste comercial piorou o forecast").

Na base de demonstração, os ajustes melhoraram a acurácia em 1,1 p.p. (56% agregaram valor), mas os ajustes de
campanha pioraram 12,6 p.p.

## Central de alertas

Erro de forecast elevado · Superestimação severa · Subestimação severa · Meta acima do P90 · Mudança estrutural no
forecast (sinal de rastreamento) · Desafiante melhorando · Oportunidade comercial — cada um com o problema, a
entidade afetada, a magnitude, o impacto potencial, a explicação e a investigação recomendada, tudo em português.

Cada alerta tem o link **"Investigar no deep dive"**: erro elevado, superestimação, subestimação e mudança
estrutural abrem a lente Previsão já na série; meta acima do P90 abre Consenso × Meta no cliente; oportunidade
abre Consenso × Orçamento no cliente. "Desafiante melhorando" é uma decisão de modelo e abre o Workspace de
forecast.
