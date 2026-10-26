# Jornada do usuário: Entrada → Relatório → Desvios

> ForecastLab · Desenvolvido por Wallison Sampaio — Especialista em Inteligência Comercial | Supply Chain | Data & AI
> Analytics · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

Este documento explica **por que** a interface do ForecastLab é organizada como uma jornada de três etapas e
**quais boas práticas de mercado** sustentam cada decisão de design. As regras e fórmulas detalhadas ficam em
[sop.md](sop.md) (relatório, deep dive, ponte preço/volume/mix e causa raiz), [api.md](api.md) (contratos) e
[ai_analyst.md](ai_analyst.md) (perguntas de atalho para a IA).

## 1. O problema que a jornada resolve

A versão anterior tinha dez telas no mesmo nível do menu (Visão Geral, Dados, Forecast, Modelos, Cenários, S&OP,
FVA, Analista de IA, Alertas e Configurações), com mais de 30 cards de KPI e cerca de 25 gráficos. Tudo estava
certo, mas o usuário não sabia **por onde começar**, **em que número confiar** nem **qual era a mensagem** para a
reunião de S&OP. O mesmo gap aparecia em três telas, com recortes diferentes.

A reunião de S&OP precisa de outra ordem:

1. **Posso confiar no número?** (dados e modelos)
2. **Qual é a mensagem e o que precisamos decidir?** (relatório executivo)
3. **Onde, por quê e quando desviamos, e o que faço agora?** (deep dive)

## 2. As três etapas

| Etapa | Rota | Pergunta de negócio | Saída |
|---|---|---|---|
| 1 · Entrada (dados e modelos) | `/app/entrada` | "A base está pronta, os modelos competiram e posso confiar no número?" | Veredito de confiança e o botão "Abrir o relatório" |
| 2 · Relatório executivo | `/app/relatorio/:capitulo` | "Qual é a mensagem para a reunião e o que precisamos decidir?" | Em cada capítulo, "Investigar no deep dive" |
| 3 · Desvios (deep dive) | `/app/desvios?…` | "Onde, por quê e quando desviamos — e o que faço agora?" | Ações: criar ajuste comercial, simular, abrir a série, perguntar à IA |

O menu lateral tem três grupos:

| Grupo | Itens |
|---|---|
| **Jornada** | 1 Entrada · dados e modelos · 2 Relatório executivo · 3 Desvios. Os itens 2 e 3 mostram um cadeado até a primeira competição de modelos terminar. |
| **Ferramentas** | Workspace de forecast · Cenários e metas · Alertas · Analista de IA |
| **Governança** (recolhível) | Modelos e FVA · Bases de dados |

`/app` sempre abre na Entrada. Quando tudo já está pronto, a Entrada se resume a um veredito de uma tela, e o botão
principal é "Abrir o relatório". Se o relatório ou o deep dive forem abertos antes da hora, a página mostra um
aviso ("Antes do relatório, a confiança") com o progresso da execução e o botão "Ir para a Entrada", em vez de
números incompletos.

### 2.1 Etapa 1 · Entrada: a confiança antes da história

Três passos em um único fluxo (`Base de dados` · `Competição de modelos` · `Confiança no forecast`); só o passo
atual fica aberto.

* **Base de dados.** Duas opções lado a lado: carregar a base de demonstração ou enviar uma planilha (com o modelo
  de planilha para download). O resultado da validação aparece na hora: base válida, aceita com avisos, ou
  bloqueada por erros críticos (a base anterior continua ativa). Quando a base já está validada, o passo vira uma
  linha: séries, meses, período, score de qualidade e a origem do orçamento e da meta.
* **Competição de modelos.** Uma frase explica a regra ("cada série testa só os modelos plausíveis para o seu
  padrão… vence o menor WMAPE, depois o menor viés"). O **placar conta vitórias por modelo**, e não um ranking de
  WMAPE entre modelos: como o roteador só envia cada modelo a certos padrões de demanda, o WMAPE de um modelo de
  séries intermitentes não é comparável ao de um modelo de séries estáveis. O ingênuo aparece em cinza como
  referência mínima.
* **Confiança no forecast.** Um veredito com cor, ícone e texto ("Confiável para decisão", "Use com cautela" ou
  "Não confiável"), 4 KPIs (acurácia fora da amostra, viés, ganho sobre o método ingênuo e receita prevista com
  confiança alta), um único gráfico (Real × Estatístico × Ingênuo fora da amostra) e a lista "Onde ter cautela"
  com até 5 séries, cada uma com o link "Investigar".

Na base de demonstração: *"O forecast acerta 85,2% fora da amostra, erra 12,5 p.p. menos que o método ingênuo e
69% da receita prevista vem de séries com confiança alta."*

### 2.2 Etapa 2 · Relatório executivo: a mensagem em 7 capítulos

Um único payload (`GET /api/story`) traz os 7 capítulos; trocar de capítulo não faz nova requisição. Cada
capítulo tem um **título que afirma a conclusão com números**, a pergunta que ele responde, **um único visual**,
até 3 leituras e os botões "Investigar no deep dive" e "Perguntar à IA".

| # | Capítulo | Pergunta | Visual | Título na base de demonstração |
|---|---|---|---|---|
| 1 | Resumo | Qual é a mensagem principal para a reunião de S&OP? | 4 KPIs + o roteiro (SCQA) | "Vamos crescer 7,3% nos próximos 12 meses, mas fechar R$ 4,09 mi abaixo do orçamento: 2 clientes concentram 59% das perdas e a meta tem 29% de chance." |
| 2 | Realizado | Como fechamos os últimos 12 meses frente ao orçamento — e por quê? | Ponte Orçamento → Volume → Mix → Preço → Real | "Vendemos 4,0% mais unidades que o orçado, mas a receita ficou 3,9% abaixo do orçamento (R$ 3,58 mi): preço (-R$ 5,00 mi) e mix (-R$ 2,26 mi) anularam o ganho de volume." |
| 3 | Precisão | Quanto o forecast errou, em que direção e por quê? | Erro por causa (controlável × inerente) | "O forecast errou 14,8% fora da amostra — 12,5 p.p. a menos que o método ingênuo — e 45% do erro tem causa controlável: promoção não antecipada lidera (19%)." |
| 4 | Próximos 12 meses | Para onde vamos, frente ao orçamento e à meta? | Colunas mensais de variação (consenso × orçamento) | "O consenso projeta R$ 94,30 mi até set/2027 (+7,3% vs últimos 12 meses): R$ 4,09 mi abaixo do orçamento e R$ 11,70 mi abaixo da meta." |
| 5 | Gap vs orçamento | Quem explica o gap vs orçamento — e é premissa ou demanda? | Barras de variação por cliente | "2 clientes concentram 59% das perdas vs orçamento: Litoral Market e Rede Horizonte Supermercados orçaram +23,5% e +21,4% de crescimento; o forecast indica -3,7% e +6,2%." |
| 6 | Meta | Qual a chance de bater a meta e o que seria preciso? | Faixa de viabilidade P10–P90 | "A meta de R$ 106,00 mi é desafiadora: 29% de chance — fechar R$ 11,70 mi exige +13,3% de distribuição numérica." |
| 7 | Decisões | O que precisamos decidir hoje? | Tabela de até 5 decisões | "5 decisões para hoje — a maior envolve R$ 11,70 mi: decidir sobre a meta, corrigir o viés de 68 séries e cadastrar o calendário promocional." |

Outros comportamentos:

* **Escopo.** "Empresa toda" ou uma região, canal ou categoria. O escopo fica na URL, é herdado pelas ferramentas
  e entra no caminho do deep dive ao clicar em "Investigar".
* **Modo apresentação.** O botão "Apresentar" (ou a tecla `P`) esconde menu e barra superior; `←`/`→` trocam de
  capítulo; `Esc` sai.
* **Exportação.** "Baixar relatório (HTML)" gera um arquivo autocontido com os mesmos 7 capítulos da tela, os
  mesmos títulos e a tabela de cada visual.
* **Rastreabilidade.** Uma linha discreta no rodapé informa base, execução, origem do orçamento e que o erro de
  previsão é medido fora da amostra, com a antecedência real da execução ("1–3 meses").

### 2.3 Etapa 3 · Desvios: o deep dive que explica o desvio

Uma página com o estado inteiro na URL (pode ser copiada e compartilhada) e **duas lentes**:

| Lente | Comparações | Pergunta |
|---|---|---|
| **Plano** | Consenso × Orçamento (próximos meses) · Consenso × Meta (próximos meses) · Real × Orçamento (últimos 12 meses) | O desvio é de premissa (orçamento otimista, preço, mix) ou de demanda? |
| **Previsão** | Real × Estatístico (campeão) · Real × Consenso histórico (com ajustes) | O forecast errou por quê, e quanto desse erro era evitável? |

O layout segue sempre a mesma ordem de perguntas:

```text
Título dinâmico (a conclusão do recorte atual)
Controles: Lente · Comparação · Período · Medida        Trilha: Empresa toda › Região: Nordeste ×   Agrupar por
4 KPIs: tamanho · probabilidade · concentração · principal fator
ONDE está o desvio?          | POR QUE desviou?
QUANDO aconteceu?
QUAIS séries tratar primeiro?  (tabela de exceções)
Ficha da série (gaveta lateral, sob demanda)
```

* **Clique** em uma linha de ONDE foca o membro (POR QUE, QUANDO e a tabela de exceções passam a falar dele);
  **"›"** detalha (Região → Canal → Cliente → Categoria → SKU → Série); o botão Voltar do navegador desfaz o
  detalhamento.
* **Clique** em um mês de QUANDO restringe o período; **clique** em uma causa filtra a tabela de exceções.
* A **ficha da série** traz a linha do tempo de 24 meses, as evidências mês a mês ("Promoção ativa · sem ajuste
  registrado · preço -12% vs referência"), a ação recomendada e os botões "Abrir no workspace", "Criar ajuste
  comercial", "Simular cenário" e "Perguntar à IA".
* Salvar um ajuste comercial pela ficha recalcula o consenso em todas as telas.

## 3. Boas práticas de mercado aplicadas

| Prática | Origem | Onde aparece no ForecastLab |
|---|---|---|
| **Pirâmide de Minto e SCQA** (Situação, Complicação, Questão, Resposta) | Barbara Minto, *The Pyramid Principle* | O capítulo Resumo abre com a ideia central (*governing thought*) e o SCQA em três linhas; o card "O roteiro" lista os títulos dos capítulos 2–7 como a lógica vertical que sustenta a ideia central. Cada título de capítulo afirma uma conclusão, não um tema. |
| **Storytelling with Data** | Cole Nussbaumer Knaflic | Contexto antes do gráfico (pergunta + linha de contexto); um visual por capítulo, escolhido para a mensagem; *declutter* (sem linhas de grade, rótulos diretos em vez de legenda, eixo oculto quando as barras têm rótulo, no máximo 12 categorias + "Demais"); a atenção vai para o que importa (foco com anel só no elemento selecionado, cor só para a variação). |
| **IBCS / regras SUCCESS** | International Business Communication Standards (Rolf Hichert) | Notação de cenários uniforme em todos os gráficos da jornada: **Real (AC)** sólido escuro, **Ano anterior (PY)** cinza, **Orçamento (PL)** contorno, **Meta (TG)** contorno tracejado, **Forecast/Consenso (FC)** hachurado. Variação favorável/desfavorável sempre com sinal e com a palavra "acima/abaixo"; títulos com a mensagem; mesma escala e mesma ordem de leitura nas pontes. |
| **Mantra de Shneiderman** | Ben Shneiderman (1996): "Overview first, zoom and filter, then details-on-demand" | O deep dive começa no total da empresa (visão geral), detalha por clique e trilha (zoom e filtro) e abre a ficha da série só quando pedida (detalhe sob demanda). |
| **Gestão por exceção e Pareto** | Princípio de Pareto e os "poucos vitais" de Joseph Juran | Concentração "n de N membros explicam X% das perdas"; marcador de acumulado e linha tracejada onde o acumulado passa de 50%; tabela "Quais séries tratar primeiro?" lista só exceções (materialidade + desvio relevante ou alta probabilidade), ordenadas por impacto. |
| **Ponte preço/volume/mix** | Análise de variação de receita (FP&A) | Pontes exatas e aditivas no grão Cliente × SKU × mês: Volume, Mix, Preço e Eventos somam exatamente o desvio. O índice de preço é de Paasche (sem efeito mix), e a parte do efeito preço vinda de meses com promoção aparece separada. |
| **Viés × ruído** | Prática de Demand Planning (tracking signal, decomposição do erro) | O erro absoluto é dividido em parte **sistemática** (viés que se repete na série) e **ruído que se compensa**; o sinal de rastreamento marca viés persistente; o viés aparece como "Superestimou/Subestimou", nunca em verde (as duas direções são erro). |
| **Causas controláveis × inerentes** | Análise de causa raiz do erro de forecast | Cada mês-série recebe uma única causa, por prioridade e só quando o sinal do erro é coerente com ela (promoção não antecipada só explica subestimação, ruptura só explica superestimação). Grupos: "Controlável pelo processo", "Inerente à demanda" e "Sem causa identificada". O que é inerente vira estoque de segurança, não ajuste manual. |
| **Forecast Value Added (FVA)** | Michael Gilliland | Escada Ingênuo → Estatístico → Consenso; o relatório diz se os ajustes comerciais melhoraram a acurácia, quais tipos de evento pioraram e a decisão "Rever a regra de ajustes" quando um tipo de evento destrói valor. |
| **Acurácia fora da amostra** | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* | Todo erro de previsão é medido em backtest com origem móvel, com os drivers congelados na origem; a antecedência (1–3 meses) é calculada da execução, nunca fixada no texto. |
| **Precisão em unidades, impacto em R$** | Prática de S&OP | WMAPE e viés em unidades (o que o planejamento de demanda controla); o impacto financeiro do erro é valorizado ao preço realizado. |
| **Probabilidade em vez de número único** | Forecast probabilístico | Chance de atingir orçamento/meta e faixa P10–P90 do consenso em todos os KPIs de plano. |

## 4. Orçamento visual (regras verificadas por teste)

As regras abaixo valem para as três páginas da jornada e são verificadas automaticamente em
`frontend/src/test/journey.global.test.tsx`.

| Regra | Limite |
|---|---|
| Blocos visuais por página | Cada bloco é um card com `data-visual` e `data-question` (a pergunta que ele responde). Entrada ≤ 5; cada capítulo do relatório = **exatamente 1**; Desvios = 5 (kpis, onde, porque, quando, excecoes). Gaveta e janelas não contam. |
| KPIs | No máximo **4 por linha**; os KPIs da jornada não têm ícone, para que valores como "-R$ 11,70 mi" caibam em 4 colunas a 1366 px. |
| Títulos | Relatório: **afirmações** com a conclusão e no máximo 3 números (até 220 caracteres). Deep dive: **perguntas** ("Onde está o desvio?"). |
| Texto | Nada é cortado: sem `truncate` nem `line-clamp`; nomes longos quebram linha. |
| Destaques | Sem faixas coloridas laterais e sem emoji; status = superfície tingida + ícone + palavra. A cor nunca carrega significado sozinha. |
| Gráficos | Sem linhas de grade; rótulos diretos; no máximo 12 categorias + "Demais (n)"; todo gráfico tem `aria-label` e o botão "Ver tabela". |
| Números | Padrão brasileiro ("R$ 4,09 mi", "14,8%", "12,5 p.p.", "out/2026"); sinal explícito ou "acima/abaixo"; P10–P90 é sempre a faixa do **consenso**. |
| Idioma | Nenhum termo de interface em inglês no texto renderizado (o teste procura palavras como Budget, Target, Loading, Revenue). |
| Consistência | O mesmo número é o mesmo em todas as telas: projeção do relatório = consenso do cockpit; chance da meta = viabilidade; WMAPE da confiança = FVA estatístico; KPI do deep dive = gap do cockpit (testado no backend). |

## 5. O que saiu das telas e para onde foi

Os endereços antigos continuam funcionando: a Visão Geral redireciona para o capítulo Resumo, o cockpit de S&OP
para o capítulo Meta e a tela de FVA para a aba "Valor dos ajustes (FVA)" de Modelos e FVA, sempre preservando os
filtros da URL. `/app/settings` redireciona para a Entrada.

| Antes | Agora |
|---|---|
| Visão Geral (8 KPIs, linha do tempo, alertas, viabilidade, eventos, 3 gráficos) | Capítulo Resumo (4 KPIs + roteiro) e Entrada (placar e confiança) |
| Cockpit de S&OP (8 KPIs, tabela trimestral, viabilidade por região/canal, riscos e oportunidades) | Capítulos Próximos 12 meses, Gap, Meta e Decisões; trimestres viram períodos T1–T4 no deep dive; riscos e oportunidades viram a tabela de exceções |
| Tela de FVA | Aba "Valor dos ajustes (FVA)" em Modelos e FVA; capítulo Precisão; decisão D6 |
| Explorador de hierarquia no Forecast | Deep dive dos desvios (lente Plano, agrupado por região) |
| Aba de carga de arquivos em Dados | Entrada, etapa 1 |
| Mapas de calor e miniestatísticas de Modelos | Lente Previsão do deep dive, agrupada por modelo campeão ou padrão de demanda |

## 6. Metas de experiência

| Meta | Valor |
|---|---|
| Da Home até o veredito de confiança, depois da execução | ≤ 2 cliques ("Começar"; numa base vazia, "Começar" e "Carregar demonstração") |
| Do veredito até qualquer causa raiz | ≤ 3 cliques (Relatório → Investigar → linha) |
| Requisições no primeiro carregamento | Entrada ≤ 3 · Relatório 1 (+ o estado da jornada) · Desvios 3 |
| Tempo de resposta (cache quente, base de demonstração) | `/api/journey` < 100 ms · `/api/models/trust` < 500 ms · `/api/deviations/*` < 500 ms · `/api/story` < 1,5 s |

## 7. Fora do escopo desta versão

* Arquivar o forecast publicado em cada ciclo de S&OP (tabela de *snapshots*), para medir a acurácia real com
  defasagem de 1 e 3 meses, em vez do backtest.
* Filtro de antecedência (1/2/3 meses) na lente Previsão.
* Definições das métricas em *popovers*, alimentadas por `/api/semantic/catalog`.
* Layout responsivo abaixo de 1280 px para o menu lateral.
