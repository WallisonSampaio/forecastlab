# Planejamento de cenários e motor de simulação what-if

> ForecastLab · Desenvolvido por Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Cenários

| Cenário | Definição |
|---|---|
| **Base** | Forecast estatístico + ajustes comerciais aprovados (consenso). Referência somente leitura. |
| **Conservador** | Preço +2% (repasse), distribuição −3%, marketing −10%, crescimento de clientes −2%, mercado −1,5%. |
| **Agressivo** | Preço −2%, distribuição +6%, promoções nos 2 meses de pico, merchandising no mês de pico, marketing +15%, crescimento de clientes +2%, mercado +1%. |
| **Personalizado** | Qualquer combinação salva pelo usuário (criar, duplicar, editar, comparar, excluir). |

Os tipos de cenário são gravados com códigos em inglês (`base`, `conservative`, `aggressive`, `custom`) e exibidos
em português na interface; nomes e descrições dos cenários pré-definidos já são gravados em português (bases criadas
por versões anteriores são migradas automaticamente).

## Alavancas

preço · distribuição · promoção (meses + desconto) · merchandising (meses) · marketing · crescimento de clientes ·
crescimento de mercado · escopo (região / canal / categoria / cliente) · ponto de partida: forecast de consenso ou
forecast estatístico.

## Modelo

```text
unidades = partida × (1 + Δpreço)^ε_preço
                   × (min(100, D₀(1 + Δdist)) / D₀)^ε_dist
                   × (1 + uplift_promo)          nos meses com promoção
                   × (1 + uplift_merch)          nos meses com merchandising
                   × (1 + Δmarketing)^ε_mkt
                   × (1 + crescimento de clientes) × (1 + crescimento de mercado)
receita  = unidades × preço × (1 + Δpreço) × (1 − desconto promocional nos meses com promoção)
```

O impacto por alavanca usa uma atribuição exata por participação logarítmica da variação multiplicativa — a soma dos
impactos das alavancas fecha exatamente com a variação total do cenário.

## Elasticidades (estimadas a partir do histórico)

Para cada categoria, uma regressão log-log **dentro das séries** (efeitos fixos por série), com dados empilhados, da
demanda sobre preço regular, distribuição numérica, promoção, merchandising, marketing, efeitos de mês e tendência:

* Os meses com promoção usam o último preço **regular** (de gôndola), para que o desconto não seja confundido com o
  efeito da promoção.
* Erros-padrão **robustos por cluster** de série (meses da mesma série são correlacionados).
* **Encolhimento Bayesiano empírico** em direção a priors de mercado, ponderado pela precisão — coeficientes pouco
  identificados (ex.: mudanças de preço de tabela que coincidem com ações de concorrentes) são puxados para o prior.
* Os resultados são limitados a faixas plausíveis; a tela Cenários e metas mostra, no painel recolhível
  "Premissas do modelo", a estimativa ao lado do valor verdadeiro usado no gerador sintético.

## Comparador

Tabela com unidades, receita, vs Base, vs Orçamento e vs Meta de cada cenário nos próximos 12 meses. O cenário em
edição mostra a receita mensal contra a base e o impacto por alavanca.

## Pré-preenchimento a partir da jornada

A tela **Cenários e metas** aceita o recorte e as alavancas pela URL — `region`, `channel`, `customer`, `category`,
`sku`, `distribution_change_pct`, `price_change_pct`, `marketing_change_pct` (frações: `0.133` = +13,3%). Com
qualquer um deles, ela abre um **novo rascunho** chamado "Simulação a partir do deep dive", com o aviso "Cenário
pré-preenchido. Ajuste e salve se quiser mantê-lo." Os pontos de entrada são:

* o botão **"Simular alavanca"** do capítulo Meta do relatório (ex.: `/app/scenarios?distribution_change_pct=0.133`,
  a alavanca de menor esforço que fecharia o gap da meta);
* o botão **"Simular cenário"** do deep dive dos desvios e da ficha da série (escopo do recorte e, quando a causa é
  distribuição, a variação de distribuição observada).

## Alocação de metas

A segunda aba da tela distribui uma meta total por região, canal, cliente, categoria ou SKU (peso histórico,
potencial, forecast ou pesos estratégicos) e classifica a viabilidade de cada meta alocada. Detalhes em
[sop.md](sop.md#alocação-de-metas).
