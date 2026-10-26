"""Dados mestres fictícios usados pelo gerador de dados sintéticos.

Todos os clientes, marcas, produtos e localidades abaixo são inventados para
fins de portfólio. Qualquer semelhança com empresas reais é mera coincidência.

Os nomes exibidos ao usuário (regiões, canais, categorias, produtos, planejadores)
estão em português do Brasil; os códigos internos (padrões, perfis sazonais)
continuam em inglês e são apenas metadados.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMPANY = "ForecastLab Demo Ltda."


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    region: str
    channel: str
    location: str
    scale: float  # volume relativo vs. um cliente médio
    price_index: float  # posicionamento do preço líquido vs. preço de tabela
    monthly_growth: float = 0.0  # crescimento estrutural do cliente (ex.: e-commerce)
    store_openings: tuple[tuple[int, float], ...] = ()  # (índice do mês, uplift)
    budget_growth: float = 0.04  # crescimento assumido no orçamento anual
    target_stretch: float = 0.05  # meta comercial acima do orçamento


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    brand: str
    list_price: float
    base_units: float  # unidades mensais para um cliente com scale = 1
    pattern: str
    seasonal_profile: str | None = None
    delisting: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


# Regiões
SUDESTE, SUL, NORDESTE, CENTRO_OESTE, NORTE = "Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"
# Canais
VAREJO_MODERNO = "Varejo Moderno"
ATACAREJO = "Atacarejo"
VAREJO_TRADICIONAL = "Varejo Tradicional"
ECOMMERCE = "E-commerce"
FARMA = "Farma"
# Categorias
BEBIDAS, SNACKS, CUIDADOS_PESSOAIS, LIMPEZA = "Bebidas", "Snacks", "Cuidados Pessoais", "Limpeza"

REGIONS = [SUDESTE, SUL, NORDESTE, CENTRO_OESTE, NORTE]
CHANNELS = [VAREJO_MODERNO, ATACAREJO, VAREJO_TRADICIONAL, ECOMMERCE, FARMA]
CATEGORIES = [BEBIDAS, SNACKS, CUIDADOS_PESSOAIS, LIMPEZA]

CUSTOMERS: list[Customer] = [
    Customer(
        "C001",
        "Atlas Hipermercados",
        SUDESTE,
        VAREJO_MODERNO,
        "São Paulo/SP",
        2.4,
        1.00,
        store_openings=((28, 0.10),),
        target_stretch=0.12,
    ),
    Customer("C002", "Rede Horizonte Supermercados", SUL, VAREJO_MODERNO, "Curitiba/PR", 1.5, 1.00, budget_growth=0.16),
    Customer(
        "C003",
        "MaxiCompra Atacarejo",
        SUDESTE,
        ATACAREJO,
        "Campinas/SP",
        2.0,
        0.92,
        store_openings=((20, 0.12), (46, 0.09)),
        target_stretch=0.20,
    ),
    Customer("C004", "Bom Sabor Distribuidora", NORDESTE, VAREJO_TRADICIONAL, "Recife/PE", 1.1, 0.97),
    Customer("C005", "Vila Verde Mercados", CENTRO_OESTE, VAREJO_MODERNO, "Goiânia/GO", 0.9, 1.02),
    Customer(
        "C006",
        "ClickCesta Online",
        SUDESTE,
        ECOMMERCE,
        "São Paulo/SP - CD",
        0.8,
        0.97,
        monthly_growth=0.012,
        budget_growth=0.03,
        target_stretch=0.03,
    ),
    Customer("C007", "Nordeste Atacadista", NORDESTE, ATACAREJO, "Fortaleza/CE", 1.3, 0.91),
    Customer("C008", "FarmaVida Drogarias", SUDESTE, FARMA, "Belo Horizonte/MG", 1.0, 1.10),
    Customer(
        "C009",
        "Amazônia Distribuição",
        NORTE,
        VAREJO_TRADICIONAL,
        "Manaus/AM",
        0.7,
        1.04,
        budget_growth=0.0,
        target_stretch=0.0,
    ),
    Customer("C010", "Serra Gaúcha Supermercados", SUL, VAREJO_MODERNO, "Caxias do Sul/RS", 0.9, 1.01),
    Customer(
        "C011", "Planalto Atacado", CENTRO_OESTE, ATACAREJO, "Brasília/DF", 1.2, 0.92, store_openings=((50, 0.14),)
    ),
    Customer(
        "C012",
        "Litoral Market",
        NORDESTE,
        VAREJO_MODERNO,
        "Salvador/BA",
        1.0,
        1.01,
        monthly_growth=-0.004,
        budget_growth=0.15,
    ),
    Customer("C013", "CuraMais Farmácias", SUL, FARMA, "Porto Alegre/RS", 0.7, 1.08),
    Customer("C014", "Ponto Certo Conveniência", SUDESTE, VAREJO_TRADICIONAL, "Rio de Janeiro/RJ", 0.6, 1.12),
]

PRODUCTS: list[Product] = [
    Product("SKU-10101", "AquaViva Água Mineral 500ml", BEBIDAS, "AquaViva", 2.49, 5200, "seasonal", "summer"),
    Product("SKU-10102", "AquaViva Com Gás Limão 350ml", BEBIDAS, "AquaViva", 3.99, 2400, "trending", "summer_mild"),
    Product("SKU-10103", "AquaViva Água Mineral 1,5L", BEBIDAS, "AquaViva", 4.29, 3800, "stable", "summer_mild"),
    Product("SKU-10201", "Frutalle Suco de Laranja 1L", BEBIDAS, "Frutalle", 8.99, 2600, "promo_driven"),
    Product("SKU-10202", "Frutalle Suco de Uva 1L", BEBIDAS, "Frutalle", 10.49, 1500, "seasonal", "christmas"),
    Product("SKU-10203", "Frutalle Zero Manga 1L", BEBIDAS, "Frutalle", 9.49, 1300, "launch"),
    Product("SKU-20101", "Crocantes Batata Clássica 90g", SNACKS, "Crocantes", 6.99, 4200, "stable"),
    Product("SKU-20102", "Crocantes Batata Queijo 90g", SNACKS, "Crocantes", 7.49, 3100, "promo_driven"),
    Product("SKU-20103", "Crocantes Pacote Festa 300g", SNACKS, "Crocantes", 18.90, 1100, "seasonal", "party"),
    Product("SKU-20201", "NutriBar Chocolate 3 un.", SNACKS, "NutriBar", 7.90, 2000, "distribution_driven"),
    Product("SKU-20202", "NutriBar Proteína 45g", SNACKS, "NutriBar", 6.49, 1600, "trending"),
    Product("SKU-20203", "NutriBar Coco 3 un.", SNACKS, "NutriBar", 7.90, 1700, "declining"),
    Product(
        "SKU-30101",
        "PuraPele Hidratante Corporal 200ml",
        CUIDADOS_PESSOAIS,
        "PuraPele",
        19.90,
        1400,
        "seasonal",
        "winter",
    ),
    Product(
        "SKU-30102",
        "PuraPele Protetor Solar FPS50 120ml",
        CUIDADOS_PESSOAIS,
        "PuraPele",
        39.90,
        900,
        "seasonal",
        "strong_summer",
    ),
    Product("SKU-30103", "PuraPele Kit Presente", CUIDADOS_PESSOAIS, "PuraPele", 59.90, 260, "intermittent", "gifting"),
    Product("SKU-30201", "Brisa Desodorante Roll-on 50ml", CUIDADOS_PESSOAIS, "Brisa", 12.90, 2300, "stable"),
    Product(
        "SKU-30202", "Brisa Desodorante Aerosol 150ml", CUIDADOS_PESSOAIS, "Brisa", 16.90, 2100, "structural_change"
    ),
    Product("SKU-30203", "Brisa Men Sport 150ml", CUIDADOS_PESSOAIS, "Brisa", 17.90, 1200, "volatile"),
    Product("SKU-40101", "LimpaMax Multiuso 500ml", LIMPEZA, "LimpaMax", 8.49, 2700, "stable"),
    Product("SKU-40102", "LimpaMax Desinfetante 2L", LIMPEZA, "LimpaMax", 14.90, 1500, "structural_change"),
    Product("SKU-40103", "LimpaMax Industrial 5L", LIMPEZA, "LimpaMax", 42.90, 180, "intermittent"),
    Product("SKU-40201", "Fresco Aromatizador Lavanda 360ml", LIMPEZA, "Fresco", 15.90, 1300, "volatile"),
    Product("SKU-40202", "Fresco Aromatizador Automotivo", LIMPEZA, "Fresco", 21.90, 220, "intermittent"),
    Product("SKU-40203", "Fresco Refil Clássico 250ml", LIMPEZA, "Fresco", 11.90, 1400, "declining", delisting=True),
]

# Probabilidade de um cliente de determinado canal listar um SKU de uma categoria.
CHANNEL_ASSORTMENT: dict[str, dict[str, float]] = {
    VAREJO_MODERNO: {BEBIDAS: 0.85, SNACKS: 0.85, CUIDADOS_PESSOAIS: 0.80, LIMPEZA: 0.85},
    ATACAREJO: {BEBIDAS: 0.80, SNACKS: 0.75, CUIDADOS_PESSOAIS: 0.35, LIMPEZA: 0.75},
    VAREJO_TRADICIONAL: {BEBIDAS: 0.70, SNACKS: 0.70, CUIDADOS_PESSOAIS: 0.30, LIMPEZA: 0.50},
    ECOMMERCE: {BEBIDAS: 0.65, SNACKS: 0.65, CUIDADOS_PESSOAIS: 0.70, LIMPEZA: 0.60},
    FARMA: {BEBIDAS: 0.0, SNACKS: 0.0, CUIDADOS_PESSOAIS: 0.95, LIMPEZA: 0.0},
}
# Farmácias também listam alguns itens de conveniência.
PHARMACY_CHANNEL = FARMA
PHARMACY_EXTRA_SKUS = {"SKU-10101", "SKU-10103", "SKU-20201", "SKU-20202"}
# SKUs institucionais / a granel que só fazem sentido no atacado e no varejo.
BULK_SKUS = {"SKU-40103"}
BULK_CHANNELS = {ATACAREJO, VAREJO_TRADICIONAL, VAREJO_MODERNO}
# Canais em que feriados reduzem levemente o sell-in.
HOLIDAY_SENSITIVE_CHANNELS = (VAREJO_TRADICIONAL, ATACAREJO)

# Perfis sazonais (mês 1..12). Normalizados para média 1 pelo gerador.
SEASONAL_PROFILES: dict[str, list[float]] = {
    "summer": [1.45, 1.35, 1.15, 0.95, 0.80, 0.70, 0.70, 0.75, 0.90, 1.05, 1.20, 1.50],
    "summer_mild": [1.15, 1.12, 1.05, 0.97, 0.92, 0.88, 0.88, 0.90, 0.95, 1.02, 1.08, 1.16],
    "strong_summer": [2.20, 1.80, 1.10, 0.60, 0.40, 0.35, 0.40, 0.50, 0.70, 1.00, 1.40, 2.40],
    "winter": [0.70, 0.70, 0.85, 1.00, 1.25, 1.50, 1.55, 1.30, 1.00, 0.85, 0.75, 0.70],
    "christmas": [0.80, 0.80, 0.85, 0.90, 0.90, 0.90, 0.90, 0.90, 0.95, 1.05, 1.35, 2.00],
    "party": [1.20, 1.05, 0.95, 0.85, 0.85, 1.15, 1.00, 0.85, 0.85, 0.90, 1.00, 1.60],
    "gifting": [0.30, 0.30, 0.40, 0.60, 1.60, 0.50, 0.40, 0.50, 0.50, 0.70, 1.80, 3.20],
}

# Uplift de eventos do calendário por categoria (multiplicativo, aplicado todo ano).
EVENT_UPLIFTS: dict[str, dict[str, float]] = {
    "black_friday": {BEBIDAS: 0.05, SNACKS: 0.10, CUIDADOS_PESSOAIS: 0.18, LIMPEZA: 0.15},
    "christmas": {BEBIDAS: 0.20, SNACKS: 0.25, CUIDADOS_PESSOAIS: 0.20, LIMPEZA: 0.05},
    "carnaval": {BEBIDAS: 0.15, SNACKS: 0.10, CUIDADOS_PESSOAIS: 0.0, LIMPEZA: 0.0},
    "mothers_day": {BEBIDAS: 0.0, SNACKS: 0.0, CUIDADOS_PESSOAIS: 0.12, LIMPEZA: 0.0},
}

# Sensibilidades "verdadeiras" dos drivers (o backend as estima de volta a partir dos dados).
PRICE_ELASTICITY = {BEBIDAS: -1.2, SNACKS: -1.5, CUIDADOS_PESSOAIS: -0.8, LIMPEZA: -1.0}
DISTRIBUTION_ELASTICITY = 0.9
MARKETING_ELASTICITY = 0.07

# Metadados internos (códigos em inglês; os testes verificam estes valores).
PATTERN_LABELS = {
    "stable": "Stable",
    "trending": "Trending",
    "declining": "Declining",
    "seasonal": "Seasonal",
    "intermittent": "Intermittent",
    "promo_driven": "Promo Driven",
    "distribution_driven": "Distribution Driven",
    "structural_change": "Structural Change",
    "volatile": "Volatile",
    "launch": "New Product (Launch)",
}

# Planejadores (nomes compartilhados com a biblioteca de eventos do backend).
PLANNER_KAM = "Key Account (KAM)"
PLANNER_SALES_DIRECTOR = "Diretor de Vendas"
PLANNER_TRADE_MARKETING = "Trade Marketing"
PLANNER_DEMAND_PLANNER = "Planejador de Demanda"
PLANNER_MARKETING = "Marketing"
PLANNER_SOURCES = [
    PLANNER_KAM,
    PLANNER_SALES_DIRECTOR,
    PLANNER_TRADE_MARKETING,
    PLANNER_DEMAND_PLANNER,
    PLANNER_MARKETING,
]

# Tipos de evento comercial (vocabulário compartilhado com o backend e o frontend).
EV_PROMOCAO = "Promoção"
EV_MERCHANDISING = "Merchandising"
EV_GANHO_DISTRIBUICAO = "Ganho de distribuição"
EV_PERDA_DISTRIBUICAO = "Perda de distribuição"
EV_NOVA_LOJA = "Nova loja"
EV_GANHO_CLIENTE = "Ganho de cliente"
EV_PERDA_CLIENTE = "Perda de cliente"
EV_CAMPANHA = "Campanha"
EV_MUDANCA_PRECO = "Mudança de preço"
EV_LANCAMENTO = "Lançamento"
EV_DESLISTAGEM = "Deslistagem"
EV_ACAO_CONCORRENTE = "Ação de concorrente"
EVENT_TYPES = [
    EV_PROMOCAO,
    EV_MERCHANDISING,
    EV_GANHO_DISTRIBUICAO,
    EV_PERDA_DISTRIBUICAO,
    EV_NOVA_LOJA,
    EV_GANHO_CLIENTE,
    EV_PERDA_CLIENTE,
    EV_CAMPANHA,
    EV_MUDANCA_PRECO,
    EV_LANCAMENTO,
    EV_DESLISTAGEM,
    EV_ACAO_CONCORRENTE,
]
