"""Fictitious master data used by the synthetic data generator.

Every customer, brand, product and location below is invented for portfolio
purposes. Any resemblance to real companies is coincidental.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMPANY = "ForecastLab Demo Co."


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    region: str
    channel: str
    location: str
    scale: float  # relative volume vs. an average customer
    price_index: float  # net price positioning vs. list price
    monthly_growth: float = 0.0  # structural customer growth (e.g. e-commerce)
    store_openings: tuple[tuple[int, float], ...] = ()  # (month index, uplift)
    budget_growth: float = 0.04  # growth assumed by the annual budget
    target_stretch: float = 0.05  # sales target on top of budget


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    brand: str
    list_price: float
    base_units: float  # monthly units for a scale = 1 customer
    pattern: str
    seasonal_profile: str | None = None
    delisting: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


REGIONS = ["Southeast", "South", "Northeast", "Midwest", "North"]
CHANNELS = ["Modern Trade", "Cash & Carry", "Traditional Trade", "E-commerce", "Pharmacy"]
CATEGORIES = ["Beverages", "Snacks", "Personal Care", "Home Care"]

CUSTOMERS: list[Customer] = [
    Customer(
        "C001",
        "Atlas Hipermercados",
        "Southeast",
        "Modern Trade",
        "São Paulo/SP",
        2.4,
        1.00,
        store_openings=((28, 0.10),),
        target_stretch=0.12,
    ),
    Customer(
        "C002", "Rede Horizonte Supermercados", "South", "Modern Trade", "Curitiba/PR", 1.5, 1.00, budget_growth=0.16
    ),
    Customer(
        "C003",
        "MaxiCompra Atacarejo",
        "Southeast",
        "Cash & Carry",
        "Campinas/SP",
        2.0,
        0.92,
        store_openings=((20, 0.12), (46, 0.09)),
        target_stretch=0.20,
    ),
    Customer("C004", "Bom Sabor Distribuidora", "Northeast", "Traditional Trade", "Recife/PE", 1.1, 0.97),
    Customer("C005", "Vila Verde Mercados", "Midwest", "Modern Trade", "Goiânia/GO", 0.9, 1.02),
    Customer(
        "C006",
        "ClickCesta Online",
        "Southeast",
        "E-commerce",
        "São Paulo/SP - DC",
        0.8,
        0.97,
        monthly_growth=0.012,
        budget_growth=0.03,
        target_stretch=0.03,
    ),
    Customer("C007", "Nordeste Atacadista", "Northeast", "Cash & Carry", "Fortaleza/CE", 1.3, 0.91),
    Customer("C008", "FarmaVida Drogarias", "Southeast", "Pharmacy", "Belo Horizonte/MG", 1.0, 1.10),
    Customer(
        "C009",
        "Amazônia Distribuição",
        "North",
        "Traditional Trade",
        "Manaus/AM",
        0.7,
        1.04,
        budget_growth=0.0,
        target_stretch=0.0,
    ),
    Customer("C010", "Serra Gaúcha Supermercados", "South", "Modern Trade", "Caxias do Sul/RS", 0.9, 1.01),
    Customer(
        "C011", "Planalto Atacado", "Midwest", "Cash & Carry", "Brasília/DF", 1.2, 0.92, store_openings=((50, 0.14),)
    ),
    Customer(
        "C012",
        "Litoral Market",
        "Northeast",
        "Modern Trade",
        "Salvador/BA",
        1.0,
        1.01,
        monthly_growth=-0.004,
        budget_growth=0.15,
    ),
    Customer("C013", "CuraMais Farmácias", "South", "Pharmacy", "Porto Alegre/RS", 0.7, 1.08),
    Customer("C014", "Ponto Certo Conveniência", "Southeast", "Traditional Trade", "Rio de Janeiro/RJ", 0.6, 1.12),
]

PRODUCTS: list[Product] = [
    Product("SKU-10101", "AquaViva Mineral Water 500ml", "Beverages", "AquaViva", 2.49, 5200, "seasonal", "summer"),
    Product(
        "SKU-10102", "AquaViva Sparkling Lemon 350ml", "Beverages", "AquaViva", 3.99, 2400, "trending", "summer_mild"
    ),
    Product("SKU-10103", "AquaViva Mineral Water 1.5L", "Beverages", "AquaViva", 4.29, 3800, "stable", "summer_mild"),
    Product("SKU-10201", "Frutalle Orange Juice 1L", "Beverages", "Frutalle", 8.99, 2600, "promo_driven"),
    Product("SKU-10202", "Frutalle Grape Juice 1L", "Beverages", "Frutalle", 10.49, 1500, "seasonal", "christmas"),
    Product("SKU-10203", "Frutalle Zero Mango 1L", "Beverages", "Frutalle", 9.49, 1300, "launch"),
    Product("SKU-20101", "Crocantes Classic Chips 90g", "Snacks", "Crocantes", 6.99, 4200, "stable"),
    Product("SKU-20102", "Crocantes Cheese Chips 90g", "Snacks", "Crocantes", 7.49, 3100, "promo_driven"),
    Product("SKU-20103", "Crocantes Party Pack 300g", "Snacks", "Crocantes", 18.90, 1100, "seasonal", "party"),
    Product("SKU-20201", "NutriBar Chocolate 3-pack", "Snacks", "NutriBar", 7.90, 2000, "distribution_driven"),
    Product("SKU-20202", "NutriBar Protein Bar 45g", "Snacks", "NutriBar", 6.49, 1600, "trending"),
    Product("SKU-20203", "NutriBar Coconut 3-pack", "Snacks", "NutriBar", 7.90, 1700, "declining"),
    Product(
        "SKU-30101", "PuraPele Body Moisturizer 200ml", "Personal Care", "PuraPele", 19.90, 1400, "seasonal", "winter"
    ),
    Product(
        "SKU-30102",
        "PuraPele Sunscreen SPF50 120ml",
        "Personal Care",
        "PuraPele",
        39.90,
        900,
        "seasonal",
        "strong_summer",
    ),
    Product("SKU-30103", "PuraPele Gift Kit", "Personal Care", "PuraPele", 59.90, 260, "intermittent", "gifting"),
    Product("SKU-30201", "Brisa Roll-on Deodorant 50ml", "Personal Care", "Brisa", 12.90, 2300, "stable"),
    Product("SKU-30202", "Brisa Aerosol Deodorant 150ml", "Personal Care", "Brisa", 16.90, 2100, "structural_change"),
    Product("SKU-30203", "Brisa Men Sport 150ml", "Personal Care", "Brisa", 17.90, 1200, "volatile"),
    Product("SKU-40101", "LimpaMax Multi-Surface 500ml", "Home Care", "LimpaMax", 8.49, 2700, "stable"),
    Product("SKU-40102", "LimpaMax Disinfectant 2L", "Home Care", "LimpaMax", 14.90, 1500, "structural_change"),
    Product("SKU-40103", "LimpaMax Industrial 5L", "Home Care", "LimpaMax", 42.90, 180, "intermittent"),
    Product("SKU-40201", "Fresco Air Spray Lavender 360ml", "Home Care", "Fresco", 15.90, 1300, "volatile"),
    Product("SKU-40202", "Fresco Car Clip", "Home Care", "Fresco", 21.90, 220, "intermittent"),
    Product(
        "SKU-40203", "Fresco Classic Refill 250ml", "Home Care", "Fresco", 11.90, 1400, "declining", delisting=True
    ),
]

# Probability that a customer of a given channel lists a SKU of a category.
CHANNEL_ASSORTMENT: dict[str, dict[str, float]] = {
    "Modern Trade": {"Beverages": 0.85, "Snacks": 0.85, "Personal Care": 0.80, "Home Care": 0.85},
    "Cash & Carry": {"Beverages": 0.80, "Snacks": 0.75, "Personal Care": 0.35, "Home Care": 0.75},
    "Traditional Trade": {"Beverages": 0.70, "Snacks": 0.70, "Personal Care": 0.30, "Home Care": 0.50},
    "E-commerce": {"Beverages": 0.65, "Snacks": 0.65, "Personal Care": 0.70, "Home Care": 0.60},
    "Pharmacy": {"Beverages": 0.0, "Snacks": 0.0, "Personal Care": 0.95, "Home Care": 0.0},
}
# Pharmacies also list a few convenience items.
PHARMACY_EXTRA_SKUS = {"SKU-10101", "SKU-10103", "SKU-20201", "SKU-20202"}
# Bulk / institutional SKUs that only make sense in wholesale and modern trade.
BULK_SKUS = {"SKU-40103"}
BULK_CHANNELS = {"Cash & Carry", "Traditional Trade", "Modern Trade"}

# Seasonal profiles (month 1..12). Normalised to mean 1 by the generator.
SEASONAL_PROFILES: dict[str, list[float]] = {
    "summer": [1.45, 1.35, 1.15, 0.95, 0.80, 0.70, 0.70, 0.75, 0.90, 1.05, 1.20, 1.50],
    "summer_mild": [1.15, 1.12, 1.05, 0.97, 0.92, 0.88, 0.88, 0.90, 0.95, 1.02, 1.08, 1.16],
    "strong_summer": [2.20, 1.80, 1.10, 0.60, 0.40, 0.35, 0.40, 0.50, 0.70, 1.00, 1.40, 2.40],
    "winter": [0.70, 0.70, 0.85, 1.00, 1.25, 1.50, 1.55, 1.30, 1.00, 0.85, 0.75, 0.70],
    "christmas": [0.80, 0.80, 0.85, 0.90, 0.90, 0.90, 0.90, 0.90, 0.95, 1.05, 1.35, 2.00],
    "party": [1.20, 1.05, 0.95, 0.85, 0.85, 1.15, 1.00, 0.85, 0.85, 0.90, 1.00, 1.60],
    "gifting": [0.30, 0.30, 0.40, 0.60, 1.60, 0.50, 0.40, 0.50, 0.50, 0.70, 1.80, 3.20],
}

# Calendar event uplifts by category (multiplicative, applied every year).
EVENT_UPLIFTS: dict[str, dict[str, float]] = {
    "black_friday": {"Beverages": 0.05, "Snacks": 0.10, "Personal Care": 0.18, "Home Care": 0.15},
    "christmas": {"Beverages": 0.20, "Snacks": 0.25, "Personal Care": 0.20, "Home Care": 0.05},
    "carnaval": {"Beverages": 0.15, "Snacks": 0.10, "Personal Care": 0.0, "Home Care": 0.0},
    "mothers_day": {"Beverages": 0.0, "Snacks": 0.0, "Personal Care": 0.12, "Home Care": 0.0},
}

# Ground-truth driver sensitivities (the backend estimates them back from data).
PRICE_ELASTICITY = {"Beverages": -1.2, "Snacks": -1.5, "Personal Care": -0.8, "Home Care": -1.0}
DISTRIBUTION_ELASTICITY = 0.9
MARKETING_ELASTICITY = 0.07

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

PLANNER_SOURCES = ["Key Account Manager", "Sales Director", "Trade Marketing", "Demand Planner", "Marketing"]
