# Analista de IA de Demanda

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Regra fundamental

**O LLM não pode inventar métricas.** Os números são produzidos pelos motores de forecast, cenários, S&OP, desvios e
FVA; o LLM apenas reescreve, com outras palavras, uma resposta que já foi calculada — e só quando o texto passa nas
travas de fundamentação. O analista funciona sem nenhum LLM.

```text
Pergunta do usuário (texto livre, em português)
      ↓
Classificador de intenções    pontuação por sinônimos PT/EN · sem acentos · tolerante a erros de digitação
      ↓  (não entendeu e há IA local?  →  o LLM sugere a intenção; o ForecastLab valida antes de usar)
Entidades                     clientes, SKUs, produtos, regiões, canais, categorias, marcas, meses, alavancas
      ↓
Consulta semântica            métrica governada × dimensão × filtros × período
      ↓
DuckDB / Motores              forecast · cenários · viabilidade · desvios · FVA · alertas
      ↓
Resultado estruturado         fatos + cards de KPI + especificação do gráfico + tabela
      ↓
Resposta NA HORA              texto determinístico em pt-BR  (/api/ai/ask, meta < 1,5 s)
      ↓  (em segundo plano, se a IA local estiver disponível)
Narração pelo LLM local       /api/ai/narrate · versão executiva em 2 frases
      ↓
Travas                        números · classificação · direção · cópia · idioma
      ↓
Texto refinado na tela        (ou a versão calculada continua, com o motivo)
```

## Resposta na hora, refinamento em segundo plano

1. **`POST /api/ai/ask` nunca espera o LLM.** A intenção é reconhecida por regras, os motores calculam os números
   e a narrativa determinística escreve a resposta em português — tudo em menos de 1,5 s. A resposta já vem com
   KPIs, gráfico, tabela e recomendações.
2. Junto com ela vêm `narration` (se vale refinar o texto e com qual modelo) e `facts` (os indicadores formatados e
   todos os números escritos no rascunho, no máximo 1.800 caracteres).
3. Se `narration.available`, a página chama **`POST /api/ai/narrate`** em segundo plano com o rascunho e os fatos.
   Enquanto isso a tela mostra "Refinando a explicação com a IA local ({modelo})…", com o tempo decorrido.
4. O LLM local escreve **2 frases curtas** (até 360 caracteres): a conclusão com os 1 ou 2 números principais e o
   que isso significa para o negócio. Insights e recomendações continuam os calculados.
5. O texto só substitui o calculado se passar em **todas** as travas:

   | Trava | Rejeita quando |
   |---|---|
   | Fundamentação numérica | algum número do texto não pode ser rastreado aos fatos, ao rascunho, à pergunta ou aos filtros |
   | Classificação | uma palavra de veredito (realista, desafiadora, agressiva, superestimado, subestimado, equilibrado…) não está na resposta calculada |
   | Direção | "queda/cai/abaixo" ao lado de uma variação positiva, "cresce/acima" ao lado de uma negativa, ou "acima/abaixo do orçamento/da meta" contrário ao gap calculado |
   | Valor agregado | o texto é quase uma cópia da resposta calculada (similaridade ≥ 90%) |
   | Idioma e completude | resposta em outro idioma, ou curta/incompleta demais |

6. Aprovado, aparece o selo "Refinado pela IA local · números verificados", com o botão "Ver versão calculada".
   Rejeitado, a versão calculada fica e uma linha discreta diz o motivo (ex.: "A IA local citou números sem lastro
   nos fatos calculados (…); mantida a versão calculada.").

**Só um trabalho de IA por vez ("o mais recente vence").** Uma nova pergunta, uma nova narração ou uma
interpretação de intenção cancela a narração anterior, e fechar a requisição (a página abortou) interrompe a
geração no Ollama. Assim o único worker de CPU do modelo local fica livre para a pergunta que o usuário está vendo.

**O que não é reescrito.** Rankings e listas (riscos, rankings de viés e acurácia, gaps por cliente, FVA, modelos,
padrões de demanda) já estão na forma mais clara, e um modelo pequeno tende a trocar o número de cliente. Simulações
what-if também não: a alavanca e o resultado têm sinais opostos ("preço -5,0%" → "receita +2,9%"), e um modelo
pequeno inverteu esse sentido nos testes. São narradas as intenções de resumo, previsão de valores, viabilidade da
meta, consulta de métrica, visão de entidade e drivers do forecast.

## Interpretação pela IA local quando as regras não entendem

As regras resolvem a grande maioria das perguntas. Quando nenhuma intenção atinge pontuação suficiente:

1. `/api/ai/ask` responde na hora com a ajuda ("Não consegui entender…" + perguntas de exemplo) e, se a IA local
   está disponível, marca `interpretable: true`.
2. A página repete a pergunta com `route_with_llm: true` e mostra "Interpretando sua pergunta com a IA local…".
3. O LLM classifica a pergunta em um **JSON com schema fechado**: a intenção (só as intenções conhecidas ou
   `unknown`), a dimensão, a direção, a métrica e os trechos que citam entidades e meses (temperatura 0, até 45 s).
4. **Nada do modelo é usado como veio:** a intenção precisa ter um handler; dimensão, direção e métrica precisam
   ser códigos conhecidos; os trechos de entidades e meses só valem se os extratores determinísticos os resolverem
   para membros reais da hierarquia e meses do horizonte; uma "visão de entidade" sem entidade é recusada.
5. Validada a intenção, o handler normal calcula a resposta, que segue o mesmo fluxo (resposta + narração). Os
   metadados mostram "intenção interpretada pela IA local", o modelo e o tempo. Se o LLM também não entender, a
   ajuda diz "nem com a ajuda da IA local".

## Perguntas livres em português

O analista foi feito para perguntas do dia a dia de um time comercial, sem sintaxe especial. Ele pode ser acionado:

* pela **barra "Pergunte à IA…" no topo de todas as telas** — a pergunta é enviada ao Analista de IA
  (`/app/ai?q=...`) e respondida na hora;
* pelos botões **"Perguntar à IA"** do relatório executivo e do deep dive dos desvios (veja abaixo);
* pela própria tela **Analista de IA**, que também oferece sugestões de perguntas prontas.

Exemplos que ele entende:

* *"Quanto vamos vender de Bebidas no Sul em dezembro?"*
* *"Qual o viés do cliente Atlas?"*
* *"Me fale sobre o canal Farma"*
* *"E se o preço cair 5%?"*
* *"A meta de dezembro é realista?"*
* *"Quais SKUs têm a pior acurácia?"*
* *"Onde estamos abaixo do orçamento?"*

### Classificador de intenções por pontuação

Em vez de exigir frases exatas, cada intenção tem um vocabulário de sinônimos em português e inglês ("quanto vamos
vender", "previsão", "projeção", "viés", "acurácia", "erro", "meta", "orçamento", "e se", "simular"…). A pergunta é
normalizada (minúsculas, **sem acentos**), as palavras são comparadas com **tolerância a erros de digitação**
("previsao", "acurasia", "orcamento") e cada intenção recebe uma pontuação; vence a de maior pontuação, levando em
conta também as entidades encontradas (um mês + uma categoria indicam previsão de valores; uma métrica + um cliente
indicam consulta de métrica). Quando nenhuma intenção atinge pontuação suficiente, entra a interpretação pela IA
local descrita acima; sem ela, o analista explica o que sabe responder e oferece sugestões.

### Entidades com correspondência aproximada

Clientes, SKUs (por código ou pelo nome do produto), regiões, canais, categorias e marcas são reconhecidos mesmo
com variações de escrita, sem acentos ou pelo primeiro nome ("Atlas" → "Atlas Hipermercados", "centro oeste" →
"Centro-Oeste"). Também são extraídos:

* **meses** — nomes em PT/EN, abreviações (`dez`, `dez/2026`), trimestres (Q1–Q4), "próximo mês", "mês que vem",
  "próximos 6 meses", "últimos 12 meses" (meses fechados);
* **dimensões** — "por cliente", "quais SKUs", "por região"…;
* **alavancas de what-if** com sinal — "preço cair 5%" → preço −5%; "distribuição aumentar 10%" → distribuição +10%.

Os filtros ativos na página complementam as entidades encontradas na pergunta.

## Intenções

| Intenção | Exemplo | Motor |
|---|---|---|
| Previsão de valores | *Quanto vamos vender de Bebidas no Sul em dezembro?* · *Quanto vendemos nos últimos 12 meses?* | forecast estatístico, consenso e P10/P90 do recorte e do período, comparados com orçamento e meta; em meses fechados, real × orçamento/meta e o backtest |
| Consulta de métrica | *Qual o viés do cliente Atlas?* · *Qual a acurácia do canal Farma?* | consulta semântica de uma métrica governada para a entidade pedida |
| Visão de entidade | *Me fale sobre o canal Farma* · *Como está o cliente Litoral Market?* | panorama da entidade: volume, forecast, consenso, gap vs orçamento/meta, acurácia, viés e alertas |
| Drivers do forecast | *O que está impulsionando o crescimento do forecast em julho?* | ponte ano anterior → estatístico por categoria → eventos → consenso (cascata) |
| Ranking de acurácia | *Quais SKUs têm a pior acurácia?* | consulta semântica `wmape BY sku` |
| Ranking de viés | *Quais clientes estão superestimados?* | consulta semântica `bias BY customer` |
| Viabilidade da meta | *A meta é realista?* · *A meta de dezembro é realista?* | motor de Viabilidade de metas |
| Melhor modelo | *Qual modelo funciona melhor para o SKU-20102?* | ranking de modelos da seleção |
| Simulação what-if | *O que acontece se a distribuição aumentar 10%?* | motor de cenários com elasticidades estimadas |
| FVA dos ajustes comerciais | *Quais ajustes comerciais pioraram a acurácia?* | relatório de FVA |
| Gap vs orçamento | *Onde estamos abaixo do orçamento?* · *Por que o forecast de dezembro de 2026 está abaixo do orçamento?* | consulta semântica `gap_vs_budget BY customer`, no horizonte ou no mês citado |
| Riscos e alertas | *Quais os principais riscos?* | central de alertas |
| Distribuição de modelos campeões · Perfil das séries · Resumo executivo | *Quais modelos mais ganham?* · *Quais séries são intermitentes?* · *Resuma o forecast* | registro de modelos / perfil das séries / visão geral |

Os códigos internos das intenções ficam em inglês (ex.: `target_feasibility`, `what_if`, `bias_ranking`) e aparecem
apenas nos metadados técnicos da resposta.

## Perguntas de atalho a partir da jornada

O relatório executivo e o deep dive dos desvios oferecem o botão **"Perguntar à IA"** com uma pergunta pronta. Cada
redação foi testada contra o classificador (`ai.intents.parse`) e cai na intenção indicada; os testes do backend
(`tests/test_story.py`) conferem isso, então **não altere a redação sem testar de novo**.

**Relatório executivo (um botão por capítulo)**

| Capítulo | Pergunta | Intenção |
|---|---|---|
| Resumo | "Quais os principais riscos?" | `risks` |
| Realizado | "Quanto vendemos nos últimos 12 meses?" | `forecast_value` nos 12 meses fechados (real × orçamento/meta + backtest) |
| Precisão | "Quais ajustes comerciais pioraram a acurácia?" (com histórico de ajustes) ou "Quais clientes estão superestimados?" / "…subestimados?" (sem histórico, pelo sinal do viés) | `fva_overrides` / `bias_ranking` |
| Próximos meses | "Por que o forecast de {mês por extenso} está {abaixo\|acima} do orçamento?" (ex.: "dezembro de 2026", o pior mês) | `budget_gap` restrito ao mês |
| Gap vs orçamento | "Como está {o cliente\|a categoria\|o SKU} {1º do ranking}?" | `entity_overview` |
| Meta | "A meta é realista?" | `target_feasibility` |
| Decisões | — (sem botão) | — |

**Deep dive dos desvios (no cabeçalho, no diagnóstico e no menu de cada série)**

| Recorte | Pergunta | Intenção |
|---|---|---|
| Consenso × Orçamento, membro em foco (região, canal, cliente, categoria, SKU) | "Como está {a região\|o canal\|o cliente\|a categoria\|o SKU} {membro}?" | `entity_overview` |
| Consenso × Orçamento, recorte sem foco | "Onde estamos abaixo do orçamento?" (desvio negativo) ou "Onde estamos acima do orçamento?" | `budget_gap` |
| Consenso × Meta | "A meta é realista?" | `target_feasibility` |
| Real × Orçamento | "Quanto vendemos nos últimos 12 meses?" (com o membro nos filtros) | `forecast_value` em meses fechados |
| Previsão, membro em foco | "Qual o WMAPE de {membro}?" (série: "{cliente} {SKU}") | `metric_lookup` |
| Previsão, recorte sem foco | "Quais clientes estão superestimados?" (viés positivo) ou "Quais clientes estão subestimados?" | `bias_ranking` |
| Real × Consenso histórico | "Quais ajustes comerciais pioraram a acurácia?" | `fva_overrides` |
| Agrupado por modelo campeão ou padrão de demanda | — (sem botão) | — |

**Passagem de filtros.** Antes de navegar para `/app/ai?q=…`, o botão copia o recorte para os filtros globais da
interface: o escopo do relatório (região, canal ou categoria) ou o caminho do detalhamento do deep dive (região →
canal → cliente → categoria → SKU). O Analista de IA envia esses filtros junto com a pergunta (`filters` em
`/api/ai/ask`), e eles complementam as entidades encontradas no texto — por isso "Quanto vendemos nos últimos 12
meses?" responde sobre o membro em foco. A página faz a pergunta assim que abre, inclusive quando o usuário já
estava nela.

## Camada semântica

Métricas: `actual, forecast, consensus, budget, target, wmape, accuracy, bias, gap_vs_budget, gap_vs_target, uplift,
fva, distribution, price, p10, p90`. Dimensões: `period, region, channel, customer, category, brand, sku, model,
scenario`. Cada consulta é exibida na interface como um texto legível, por exemplo
`SELECT wmape(units) BY sku WHERE all ORDER BY wmape DESC LIMIT 10`.

## Trava de fundamentação numérica

`allowed_numbers()` reúne todos os números dos fatos, do rascunho, da pergunta e dos filtros (também ×100, ÷10³,
÷10⁶ e ÷10⁹, para os formatos de %, mil, milhões e bilhões). `grounding_violations()` rejeita qualquer número do
texto do LLM que não esteja a até 1,5% de um valor permitido (inteiros pequenos ≤ 31 e anos são ignorados). Uma
resposta rejeitada mantém a narrativa determinística, e a interface mostra o motivo; nos metadados, o texto da IA
local aparece como **recusado** na verificação de fundamentação.

## LLM local

* **Escolha do modelo:** `OLLAMA_MODEL`, se estiver definido e baixado; senão, o primeiro modelo baixado desta
  lista (do mais rápido para o mais lento em CPU): `qwen3:1.7b`, `llama3.2:3b`, `qwen3:4b-instruct-2507-q4_K_M`,
  `qwen3:4b`. O `docker compose up` baixa o `llama3.2:3b` (ou o definido em `OLLAMA_MODEL`).
* **Desempenho em CPU (medido):** `qwen3:1.7b` ≈ 10 tokens/s (≈ 20 s para as 2 frases), `llama3.2:3b` ≈ 5
  tokens/s, `qwen3:4b` ≈ 4 tokens/s. Como a resposta calculada aparece na hora, a espera nunca bloqueia o usuário.
* **Configuração:** `OLLAMA_URL` (padrão `http://127.0.0.1:11434`), `OLLAMA_TIMEOUT` (teto de uma narração, padrão
  90 s), `OLLAMA_NUM_THREAD` (padrão ≈ 2/3 dos núcleos, entre 2 e 8, para a API continuar respondendo enquanto o
  modelo escreve) e `FORECASTLAB_AI_ENABLED=false` para desligar a IA local.
* **Status e aquecimento:** a verificação do Ollama roda em segundo plano e fica em cache (30 s quando disponível,
  10 s quando não); nenhuma chamada da interface espera mais que alguns décimos de segundo por ela. A primeira
  verificação bem-sucedida carrega o modelo na memória (`keep_alive` de 30 min); a tela avisa "o primeiro
  refinamento pode demorar um pouco mais".
* Sem o Ollama, o analista continua funcionando com a narrativa determinística por regras, escrita em português —
  o app **não depende de nenhum LLM**. A tela indica o modo atual ("IA local conectada · {modelo}" ou "Modo
  determinístico · respostas por regras").

## Respostas e gráficos dinâmicos

Cada resposta traz o texto em português, insights, cards de KPI com valores no padrão brasileiro (`R$ 94,30 mi`,
`14,8%`, `dez/2026`), recomendações, a tabela de apoio e um gráfico renderizado pelo `ChartRenderer` do frontend:
`line`, `bar` (horizontal ou vertical, com cores por sinal para viés e gaps) e `waterfall` (cascata). O painel "Como
esta resposta foi calculada" mostra a intenção, as entidades e os filtros reconhecidos, a consulta semântica
executada, quem interpretou a pergunta (regras ou IA local), o resultado da narração e da verificação de
fundamentação e o tempo de resposta.
