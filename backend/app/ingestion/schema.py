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

# Display names used in the Excel template / exports (PRD naming).
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

DESCRIPTIONS = {
    "date": "Month of the observation (any day of the month is accepted; data is aggregated monthly).",
    "region": "Sales region (e.g. Southeast).",
    "channel": "Sales channel (e.g. Modern Trade, E-commerce).",
    "customer": "Customer / account name.",
    "sku": "Product code.",
    "units": "Units sold (sell-in) in the month. Must be >= 0.",
    "customer_location": "Customer location / DC (optional).",
    "customer_potential": "Annual addressable units for the customer (optional, used in allocation & feasibility).",
    "product": "Product description (optional).",
    "category": "Product category (optional).",
    "brand": "Brand (optional).",
    "revenue": "Net revenue (optional; computed from Units x Price when missing).",
    "price": "Average net price (optional).",
    "promotion": "1 if the SKU was on promotion that month, else 0 (optional).",
    "distribution": "Numeric distribution % (0-100) (optional).",
    "stockout": "1 if there was a stock-out that month (optional).",
    "holiday": "Number of holidays in the month (optional).",
    "marketing_investment": "Marketing investment in currency (optional).",
    "merchandising_event": "1 if there was a merchandising event (display, end-cap) (optional).",
}

_ALIASES = {
    "date": ["date", "data", "month", "mes", "period", "periodo", "yearmonth", "anomes"],
    "region": ["region", "regiao", "regional"],
    "channel": ["channel", "canal", "saleschannel"],
    "customer": ["customer", "cliente", "client", "account", "conta"],
    "customer_location": ["customerlocation", "location", "localizacao", "local", "store", "loja", "dc"],
    "customer_potential": ["customerpotential", "potential", "potencial", "customerpotencial"],
    "sku": ["sku", "item", "material", "productcode", "codigo", "codproduto", "itemcode"],
    "product": ["product", "produto", "description", "descricao", "productname", "itemname"],
    "category": ["category", "categoria"],
    "brand": ["brand", "marca"],
    "units": ["units", "unit", "qty", "quantity", "volume", "quantidade", "unidades", "vendas", "sales_units"],
    "revenue": ["revenue", "receita", "faturamento", "netsales", "sales", "valor", "netrevenue"],
    "price": ["price", "preco", "unitprice", "precomedio", "avgprice"],
    "promotion": ["promotion", "promo", "promocao", "onpromotion"],
    "distribution": ["distribution", "distribuicao", "numericdistribution", "dn"],
    "stockout": ["stockout", "ruptura", "oos", "outofstock"],
    "holiday": ["holiday", "holidays", "feriado", "feriados"],
    "marketing_investment": ["marketinginvestment", "marketing", "investimentomarketing", "mktinvestment", "mkt"],
    "merchandising_event": ["merchandisingevent", "merchandising", "merch", "display"],
}


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


ALIAS_INDEX = {normalize_key(alias): canon for canon, aliases in _ALIASES.items() for alias in aliases}


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
