"""Canonical dataset schema and flexible column mapping (EN/PT aliases)."""

from __future__ import annotations

import re
import unicodedata

REQUIRED = ["date", "region", "channel", "customer", "sku", "units"]
OPTIONAL = [
    "customer_location",
    "customer_potential",
    "product",
    "category",
    "brand",
    "revenue",
    "price",
    "promotion",
    "distribution",
    "stockout",
    "holiday",
    "marketing_investment",
    "merchandising_event",
]
CANONICAL = REQUIRED + OPTIONAL
NUMERIC = [
    "units",
    "revenue",
    "price",
    "promotion",
    "distribution",
    "stockout",
    "holiday",
    "marketing_investment",
    "merchandising_event",
    "customer_potential",
]

# English (PRD) column names: the demo files use them and they are also accepted on upload (see the template's
# "Nome alternativo" column).
DISPLAY = {
    "date": "Date",
    "region": "Region",
    "channel": "Channel",
    "customer": "Customer",
    "customer_location": "CustomerLocation",
    "customer_potential": "CustomerPotential",
    "sku": "SKU",
    "product": "Product",
    "category": "Category",
    "brand": "Brand",
    "units": "Units",
    "revenue": "Revenue",
    "price": "Price",
    "promotion": "Promotion",
    "distribution": "Distribution",
    "stockout": "StockOut",
    "holiday": "Holiday",
    "marketing_investment": "MarketingInvestment",
    "merchandising_event": "MerchandisingEvent",
}

# Portuguese header of each column, as written in the downloadable template (each one is an alias below).
HEADERS_PT = {
    "date": "Data",
    "region": "Região",
    "channel": "Canal",
    "customer": "Cliente",
    "sku": "SKU",
    "units": "Unidades",
    "customer_location": "Local do Cliente",
    "customer_potential": "Potencial do Cliente",
    "product": "Produto",
    "category": "Categoria",
    "brand": "Marca",
    "revenue": "Receita",
    "price": "Preço",
    "promotion": "Promoção",
    "distribution": "Distribuição",
    "stockout": "Ruptura",
    "holiday": "Feriados",
    "marketing_investment": "Investimento em Marketing",
    "merchandising_event": "Merchandising",
}

DESCRIPTIONS = {
    "date": "Mês da observação (qualquer dia do mês é aceito; os dados são agregados por mês).",
    "region": "Região de vendas (ex.: Sudeste).",
    "channel": "Canal de vendas (ex.: Varejo Moderno, E-commerce).",
    "customer": "Nome do cliente / conta.",
    "sku": "Código do produto.",
    "units": "Unidades vendidas (sell-in) no mês. Deve ser maior ou igual a zero.",
    "customer_location": "Cidade ou centro de distribuição do cliente (opcional).",
    "customer_potential": "Potencial anual endereçável do cliente, em unidades (opcional; usado na alocação de "
    "metas e na viabilidade).",
    "product": "Descrição do produto (opcional).",
    "category": "Categoria do produto (opcional).",
    "brand": "Marca (opcional).",
    "revenue": "Receita líquida em R$ (opcional; calculada como Unidades x Preço quando ausente).",
    "price": "Preço líquido médio em R$ (opcional).",
    "promotion": "1 se o SKU esteve em promoção no mês, senão 0 (opcional).",
    "distribution": "Distribuição numérica em % (0 a 100) (opcional).",
    "stockout": "1 se houve ruptura no mês, senão 0 (opcional).",
    "holiday": "Número de feriados no mês (opcional).",
    "marketing_investment": "Investimento em marketing no mês, em R$ (opcional).",
    "merchandising_event": "1 se houve ação de merchandising (display, ponta de gôndola), senão 0 (opcional).",
}

# Aliases are compared after ``normalize_key`` (case-, accent-, space- and punctuation-insensitive).
_ALIASES = {
    "date": ["date", "data", "month", "mes", "period", "periodo", "yearmonth", "anomes", "mesano", "competencia"],
    "region": ["region", "regiao", "regional", "regiaodevendas"],
    "channel": ["channel", "canal", "saleschannel", "canaldevendas"],
    "customer": ["customer", "cliente", "client", "account", "conta", "nomedocliente"],
    "customer_location": [
        "customerlocation",
        "location",
        "localizacao",
        "local",
        "store",
        "loja",
        "dc",
        "localdocliente",
        "localizacaodocliente",
        "centrodedistribuicao",
    ],
    "customer_potential": [
        "customerpotential",
        "potential",
        "potencial",
        "customerpotencial",
        "potencialdocliente",
        "potencialcliente",
        "potencialanual",
    ],
    "sku": ["sku", "item", "material", "productcode", "codigo", "codproduto", "itemcode", "codigodoproduto"],
    "product": [
        "product",
        "produto",
        "description",
        "descricao",
        "productname",
        "itemname",
        "descricaodoproduto",
        "nomedoproduto",
    ],
    "category": ["category", "categoria", "categoriadoproduto"],
    "brand": ["brand", "marca"],
    "units": [
        "units",
        "unit",
        "qty",
        "quantity",
        "volume",
        "quantidade",
        "unidades",
        "vendas",
        "sales_units",
        "unidadesvendidas",
        "qtd",
        "qtde",
    ],
    "revenue": [
        "revenue",
        "receita",
        "faturamento",
        "netsales",
        "sales",
        "valor",
        "netrevenue",
        "receitaliquida",
        "faturamentoliquido",
    ],
    "price": ["price", "preco", "unitprice", "precomedio", "avgprice", "precoliquido", "precounitario"],
    "promotion": ["promotion", "promo", "promocao", "onpromotion", "empromocao"],
    "distribution": ["distribution", "distribuicao", "numericdistribution", "dn", "distribuicaonumerica"],
    "stockout": ["stockout", "ruptura", "oos", "outofstock", "rupturadeestoque"],
    "holiday": ["holiday", "holidays", "feriado", "feriados", "diasdeferiado"],
    "marketing_investment": [
        "marketinginvestment",
        "marketing",
        "investimentomarketing",
        "mktinvestment",
        "mkt",
        "investimentoemmarketing",
        "investimentomkt",
        "verbademarketing",
    ],
    "merchandising_event": [
        "merchandisingevent",
        "merchandising",
        "merch",
        "display",
        "acaodemerchandising",
        "eventodemerchandising",
    ],
}

# Optional plan sheet ("Plano (opcional)") inside an uploaded workbook: sheet-name prefixes and column aliases.
PLAN_SHEET_PREFIXES = ("plan", "budget", "orcamento", "meta")
PLAN_HEADERS_PT = {
    "date": "Data",
    "customer": "Cliente",
    "sku": "SKU",
    "budget_units": "Orçamento (unidades)",
    "target_units": "Meta (unidades)",
    "budget_revenue": "Orçamento (receita)",
    "target_revenue": "Meta (receita)",
}
PLAN_DESCRIPTIONS = {
    "date": "Mês do plano.",
    "customer": "Cliente (o mesmo nome usado na aba de dados).",
    "sku": "Código do produto (o mesmo usado na aba de dados).",
    "budget_units": "Orçamento do mês, em unidades.",
    "target_units": "Meta comercial do mês, em unidades.",
    "budget_revenue": "Orçamento do mês, em R$ (opcional; quando ausente, Orçamento (unidades) x preço médio dos "
    "últimos 6 meses).",
    "target_revenue": "Meta comercial do mês, em R$ (opcional; quando ausente, Meta (unidades) x preço médio dos "
    "últimos 6 meses).",
}
PLAN_ALIASES = {
    "date": ["date", "data", "month", "mes", "period", "periodo", "mesano", "competencia"],
    "customer": ["customer", "cliente", "client", "account", "conta"],
    "sku": ["sku", "item", "material", "productcode", "codigo"],
    "budget_units": [
        "budgetunits",
        "orcamentounidades",
        "orcamentoun",
        "unidadesorcamento",
        "budgetqty",
        "orcamentoemunidades",
        "orcamentoqtd",
        "orcamentovolume",
    ],
    "target_units": [
        "targetunits",
        "metaunidades",
        "metaun",
        "unidadesmeta",
        "targetqty",
        "metaemunidades",
        "metaqtd",
        "metavolume",
    ],
    "budget_revenue": [
        "budgetrevenue",
        "orcamentoreceita",
        "receitaorcamento",
        "orcamentors",
        "orcamentor",
        "orcamentoemreais",
        "orcamentoreais",
        "orcamentovalor",
    ],
    "target_revenue": [
        "targetrevenue",
        "metareceita",
        "receitameta",
        "metars",
        "metar",
        "metaemreais",
        "metareais",
        "metavalor",
    ],
}
PLAN_REQUIRED = ["date", "customer", "sku", "budget_units", "target_units"]


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


ALIAS_INDEX = {normalize_key(alias): canon for canon, aliases in _ALIASES.items() for alias in aliases}
PLAN_ALIAS_INDEX = {normalize_key(alias): canon for canon, aliases in PLAN_ALIASES.items() for alias in aliases}


def map_columns(columns: list[str]) -> dict[str, str]:
    """original column -> canonical name (first match wins, unknown columns ignored)."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for col in columns:
        canon = ALIAS_INDEX.get(normalize_key(col))
        if canon and canon not in used:
            mapping[col] = canon
            used.add(canon)
    return mapping


def map_plan_columns(columns: list) -> dict[str, object]:
    """canonical plan field -> original column name (first match wins, unknown columns ignored)."""
    out: dict[str, object] = {}
    for col in columns:
        canon = PLAN_ALIAS_INDEX.get(normalize_key(col))
        if canon and canon not in out:
            out[canon] = col
    return out


def is_plan_sheet(sheet_name: str) -> bool:
    """True for plan sheet names such as "Plano (opcional)", "Plano", "Orçamento", "Plan (optional)", "Budget".

    Excel's default sheet names in Portuguese ("Planilha1", and "Plan1" in older versions), any other
    "Planilha …" (e.g. "Planilha de vendas") and "Metadados"/"Metadata" are not plan sheets.
    """
    key = normalize_key(sheet_name)
    if re.fullmatch(r"plan\d+", key) or key.startswith(("planilha", "metadad", "metadata")):
        return False
    return key.startswith(PLAN_SHEET_PREFIXES)
