"""Gerador reprodutível de demanda sintética do ForecastLab.

Os dados não são ruído aleatório: cada série é construída a partir de
componentes econômicos explícitos e plausíveis, para que os modelos de
forecast, a análise de drivers e a lógica de S&OP tenham sinal real a descobrir:

    unidades = nível x tendência x sazonalidade x eventos do calendário
               x aberturas de loja x efeito distribuição x efeito preço relativo
               x promoção x merchandising x marketing x quebras estruturais
               x ruído x (1 - perda por ruptura)

O mesmo ``random_seed`` sempre produz exatamente o mesmo conjunto de dados.
Os rótulos exibidos ao usuário estão em português do Brasil; os sorteios
aleatórios dependem apenas de códigos (cliente, SKU), nunca de rótulos.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .calendar import month_features
from .catalog import (
    BULK_CHANNELS,
    BULK_SKUS,
    CHANNEL_ASSORTMENT,
    COMPANY,
    CUSTOMERS,
    DISTRIBUTION_ELASTICITY,
    ECOMMERCE,
    EV_ACAO_CONCORRENTE,
    EV_CAMPANHA,
    EV_DESLISTAGEM,
    EV_GANHO_CLIENTE,
    EV_GANHO_DISTRIBUICAO,
    EV_LANCAMENTO,
    EV_MERCHANDISING,
    EV_MUDANCA_PRECO,
    EV_NOVA_LOJA,
    EV_PERDA_CLIENTE,
    EV_PERDA_DISTRIBUICAO,
    EV_PROMOCAO,
    EVENT_UPLIFTS,
    HOLIDAY_SENSITIVE_CHANNELS,
    MARKETING_ELASTICITY,
    PATTERN_LABELS,
    PHARMACY_CHANNEL,
    PHARMACY_EXTRA_SKUS,
    PLANNER_DEMAND_PLANNER,
    PLANNER_KAM,
    PLANNER_MARKETING,
    PLANNER_SALES_DIRECTOR,
    PLANNER_TRADE_MARKETING,
    PRICE_ELASTICITY,
    PRODUCTS,
    SEASONAL_PROFILES,
    Customer,
    Product,
)

GENERATOR_VERSION = "1.0.0"
NOISE_SIGMA = {
    "stable": 0.07,
    "trending": 0.08,
    "declining": 0.09,
    "seasonal": 0.09,
    "promo_driven": 0.10,
    "distribution_driven": 0.09,
    "structural_change": 0.09,
    "volatile": 0.36,
    "launch": 0.12,
    "intermittent": 0.0,
}
PROMO_FREQUENCY = {"promo_driven": 0.30, "volatile": 0.15, "intermittent": 0.04, "launch": 0.20}
MONTHLY_INFLATION = 0.004


@dataclass
class SyntheticDataset:
    sales: pd.DataFrame
    plan: pd.DataFrame
    historical_overrides: pd.DataFrame
    future_overrides: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def _rng(seed: int, *keys: object) -> np.random.Generator:
    """Sub-gerador determinístico: independente da ordem de chamada e do processo."""
    key = zlib.crc32("|".join(str(k) for k in keys).encode("utf-8"))
    return np.random.default_rng([int(seed), key])


def _profile(name: str | None) -> np.ndarray:
    if not name:
        return np.ones(12)
    p = np.asarray(SEASONAL_PROFILES[name], dtype=float)
    return p / p.mean()


def _assortment(seed: int) -> dict[str, list[Product]]:
    listing: dict[str, list[Product]] = {c.code: [] for c in CUSTOMERS}
    for cust in CUSTOMERS:
        r = _rng(seed, "assortment", cust.code)
        for prod in PRODUCTS:
            prob = CHANNEL_ASSORTMENT[cust.channel].get(prod.category, 0.0)
            if cust.channel == PHARMACY_CHANNEL and prod.sku in PHARMACY_EXTRA_SKUS:
                prob = 0.6
            if prod.sku in BULK_SKUS and cust.channel not in BULK_CHANNELS:
                prob = 0.0
            if r.random() < prob:
                listing[cust.code].append(prod)
    # Garante que todo SKU seja listado por pelo menos três clientes.
    by_scale = sorted(CUSTOMERS, key=lambda c: -c.scale)
    for prod in PRODUCTS:
        holders = [c for c in CUSTOMERS if prod in listing[c.code]]
        for cust in by_scale:
            if len(holders) >= 3:
                break
            allowed = CHANNEL_ASSORTMENT[cust.channel].get(prod.category, 0.0) > 0
            if allowed and prod not in listing[cust.code]:
                listing[cust.code].append(prod)
                holders.append(cust)
    return listing


def _sku_price_path(seed: int, prod: Product, n: int, months: pd.DatetimeIndex) -> tuple[np.ndarray, list[dict]]:
    """Preço de tabela nominal: reajustes anuais em abril + reposicionamentos por SKU."""
    r = _rng(seed, "price", prod.sku)
    price = np.full(n, prod.list_price, dtype=float)
    events: list[dict] = []
    for i, d in enumerate(months):
        if d.month == 4 and i > 0:
            inc = r.uniform(0.035, 0.065)
            price[i:] *= 1 + inc
    if prod.sku == "SKU-30202":  # aumento de preço agressivo -> queda estrutural
        price[34:] *= 1.15
        events.append(
            {"type": EV_MUDANCA_PRECO, "detail": "Aumento de preço agressivo", "month_index": 34, "change": 0.15}
        )
    if prod.sku == "SKU-20101":  # reposicionamento de preço contra marcas próprias
        price[40:] *= 0.92
        events.append(
            {
                "type": EV_MUDANCA_PRECO,
                "detail": "Redução de preço (reposicionamento contra marcas próprias)",
                "month_index": 40,
                "change": -0.08,
            }
        )
    return price, events


def _sku_campaigns(seed: int, prod: Product, n: int) -> np.ndarray:
    r = _rng(seed, "campaign", prod.sku)
    freq = 0.12 if prod.pattern in ("trending", "launch", "promo_driven") else 0.06
    return r.random(n) < freq


def _simulate_series(
    seed: int,
    cust: Customer,
    prod: Product,
    months: pd.DatetimeIndex,
    price_path: np.ndarray,
    campaigns: np.ndarray,
    cal: list[dict],
) -> tuple[pd.DataFrame, dict[str, Any], np.ndarray]:
    r = _rng(seed, "series", cust.code, prod.sku)
    n = len(months)
    t = np.arange(n)
    moy = months.month.to_numpy()
    cat = prod.category
    info: dict[str, Any] = {"customer": cust.name, "sku": prod.sku, "pattern": prod.pattern, "events": []}

    level = prod.base_units * cust.scale * r.uniform(0.75, 1.25)

    # --- tendência / ciclo de vida ------------------------------------------------
    trend = np.ones(n)
    active = np.ones(n, dtype=bool)
    if prod.pattern == "trending":
        trend = (1 + r.uniform(0.010, 0.016)) ** t
    elif prod.pattern == "declining":
        trend = (1 - r.uniform(0.008, 0.013)) ** t
    elif prod.pattern == "launch":
        launch = 42 + int(r.integers(0, 3))
        active[:launch] = False
        age = np.clip(t - launch, 0, None)
        trend = np.where(active, 0.35 + 0.65 * (1 - np.exp(-(age + 1) / 3.5)), 0.0)
        info["events"].append({"type": EV_LANCAMENTO, "month_index": launch})
    trend *= (1 + cust.monthly_growth) ** t

    structural = np.ones(n)
    if prod.pattern == "structural_change":
        if prod.sku == "SKU-40102":
            brk = 42 + int(r.integers(0, 4))
            structural[brk:] = r.uniform(1.40, 1.55)
            info["events"].append({"type": f"{EV_GANHO_CLIENTE} (contrato institucional)", "month_index": brk})
        else:
            brk = 34
            structural[brk:] = r.uniform(0.70, 0.78)
            info["events"].append({"type": EV_ACAO_CONCORRENTE, "month_index": brk})

    if prod.delisting and r.random() < 0.45:
        delist = 49 + int(r.integers(0, 5))
        active[delist:] = False
        info["events"].append({"type": EV_DESLISTAGEM, "month_index": delist})

    # --- sazonalidade e eventos do calendário ---------------------------------------
    prof = _profile(prod.seasonal_profile)
    amp = r.uniform(0.85, 1.15)
    season = 1 + (prof[moy - 1] - 1) * amp
    events = np.ones(n)
    for i, f in enumerate(cal):
        e = 1.0
        if f["black_friday"]:
            bf = EVENT_UPLIFTS["black_friday"][cat] * (1.6 if cust.channel == ECOMMERCE else 1.0)
            e *= 1 + bf
        if f["christmas"]:
            e *= 1 + EVENT_UPLIFTS["christmas"][cat]
        if f["carnaval"]:
            e *= 1 + EVENT_UPLIFTS["carnaval"][cat]
        if f["mothers_day"]:
            e *= 1 + EVENT_UPLIFTS["mothers_day"][cat]
        if cust.channel in HOLIDAY_SENSITIVE_CHANNELS:
            e *= 1 - 0.008 * int(f["holidays"])
        events[i] = e

    stores = np.ones(n)
    for idx, up in cust.store_openings:
        stores[idx:] *= 1 + up

    # --- distribuição ---------------------------------------------------------------
    if prod.pattern == "distribution_driven":
        d0 = r.uniform(28, 38)
        dist = np.full(n, d0)
        for g_month in sorted(r.choice(np.arange(8, 56), size=4, replace=False)):
            dist[g_month:] += r.uniform(9, 15)
            info["events"].append({"type": EV_GANHO_DISTRIBUICAO, "month_index": int(g_month)})
    else:
        d0 = r.uniform(60, 92)
        dist = np.full(n, d0)
        if r.random() < 0.25:
            g_month = int(r.integers(6, 56))
            dist[g_month:] += r.uniform(5, 12)
            info["events"].append({"type": EV_GANHO_DISTRIBUICAO, "month_index": g_month})
        if r.random() < 0.10:
            l_month = int(r.integers(6, 56))
            dist[l_month:] -= r.uniform(8, 15)
            info["events"].append({"type": EV_PERDA_DISTRIBUICAO, "month_index": l_month})
    dist = np.clip(dist + r.normal(0, 1.0, n), 5, 100)
    dist_eff = (dist / d0) ** DISTRIBUTION_ELASTICITY

    # --- preço e promoção --------------------------------------------------------------
    cpi = (1 + MONTHLY_INFLATION) ** t
    list_price = price_path * cust.price_index
    real_ratio = price_path / (prod.list_price * cpi)
    price_eff = real_ratio ** PRICE_ELASTICITY[cat]

    promo_freq = PROMO_FREQUENCY.get(prod.pattern, 0.10)
    promo = (r.random(n) < promo_freq).astype(int)
    discount = np.where(promo == 1, r.uniform(0.12, 0.25, n), 0.0)
    if prod.pattern == "promo_driven":
        sens = r.uniform(0.55, 0.85, n)
    else:
        sens = r.uniform(0.15, 0.30, n)
    promo_eff = 1 + promo * sens
    if prod.pattern == "promo_driven":
        dip = np.r_[1.0, np.where(promo[:-1] == 1, 0.88, 1.0)]
        promo_eff *= dip
    net_price = list_price * (1 - 0.8 * discount)

    merch_prob = np.where(promo == 1, 0.40, 0.15 if prod.pattern == "promo_driven" else 0.07)
    merch = (r.random(n) < merch_prob).astype(int)
    merch_eff = 1 + merch * r.uniform(0.10, 0.20, n)

    base_mkt = level * prod.list_price * r.uniform(0.02, 0.04)
    mkt = base_mkt * np.where(campaigns, r.uniform(2.5, 4.0, n), r.uniform(0.85, 1.15, n))
    mkt_eff = (mkt / base_mkt) ** MARKETING_ELASTICITY

    # --- rupturas, ruído, outliers ---------------------------------------------------
    so_prob = 0.04 if prod.pattern == "volatile" else 0.025
    stockout = (r.random(n) < so_prob).astype(int)
    so_loss = np.where(stockout == 1, r.uniform(0.25, 0.6, n), 0.0)

    sigma = NOISE_SIGMA.get(prod.pattern, 0.08)
    noise = np.exp(r.normal(-(sigma**2) / 2, sigma, n)) if sigma > 0 else np.ones(n)

    event_mult = promo_eff * merch_eff  # o que um planejador bem informado conseguiria antecipar
    mean_units = level * trend * season * events * stores * dist_eff * price_eff * structural

    if prod.pattern == "intermittent":
        occ_base = r.uniform(0.28, 0.45)
        occ_p = np.clip(occ_base * prof[moy - 1] ** 0.8, 0.03, 0.95)
        occurs = r.random(n) < occ_p
        size = r.gamma(2.2, 1.0 / 2.2, n) * level / max(occ_base, 1e-6) * 0.6
        units = np.where(occurs, size * dist_eff * events, 0.0)
    else:
        units = mean_units * promo_eff * merch_eff * mkt_eff * noise * (1 - so_loss)

    if r.random() < 0.03:
        spike = int(r.integers(12, n - 2))
        units[spike] *= 2.6
        info["events"].append({"type": "Pedido pontual atípico (outlier)", "month_index": spike})

    units = np.where(active, np.round(np.clip(units, 0, None)), 0.0)
    off = ~active
    promo[off] = stockout[off] = merch[off] = 0
    dist[off] = mkt[off] = 0.0

    df = pd.DataFrame(
        {
            "Date": months,
            "Customer": cust.name,
            "SKU": prod.sku,
            "Units": units.astype(int),
            "Price": np.round(net_price, 2),
            "Promotion": promo,
            "Distribution": np.round(dist, 1),
            "StockOut": stockout,
            "MarketingInvestment": np.round(mkt, 2),
            "MerchandisingEvent": merch,
        }
    )
    # Meses anteriores ao lançamento e posteriores à deslistagem não existem num extrato real de vendas.
    first_active = int(np.argmax(active)) if active.any() else n
    keep = np.zeros(n, dtype=bool)
    keep[first_active:] = True
    if prod.delisting and not active[-1]:
        keep &= active
    df = df[keep]
    info["mean_units"] = float(np.mean(units[active])) if active.any() else 0.0
    return df, info, event_mult


def _historical_overrides(
    seed: int, sales: pd.DataFrame, event_mult: dict[tuple[str, str], np.ndarray], months: pd.DatetimeIndex
) -> pd.DataFrame:
    """Ajustes comerciais feitos pelos planejadores nos últimos 12 meses (para a análise de FVA).

    Ajustes bem informados antecipam promoções/merchandising reais (agregam
    valor); ajustes otimistas ou "políticos" normalmente destroem valor.
    """
    r = _rng(seed, "overrides")
    last12 = months[-12:]
    rows: list[dict[str, Any]] = []
    recent = sales[sales["Date"].isin(last12)]
    keyed = {
        (c, s, d): {"Promotion": p, "MerchandisingEvent": m}
        for c, s, d, p, m in zip(
            recent["Customer"],
            recent["SKU"],
            recent["Date"],
            recent["Promotion"],
            recent["MerchandisingEvent"],
            strict=True,
        )
    }
    # A ordem e a quantidade de itens de cada lista são as mesmas da versão original:
    # os sorteios (r.choice / r.integers) escolhem índices, então os números não mudam.
    promo_comments = [
        "Promoção acordada com o cliente - tabloide + desconto de preço",
        "Promoção do plano de negócios conjunto (JBP) confirmada",
        "Desconto de preço negociado para o mês",
    ]
    merch_comments = [
        "Ponta de gôndola confirmada",
        "Espaço extra de gôndola nas lojas-chave",
        "Display de checkout negociado",
    ]
    optimistic = [
        (EV_GANHO_CLIENTE, "Cliente sinalizou pedidos mais fortes"),
        (EV_CAMPANHA, "Campanha da marca deve impulsionar o sell-out"),
        (EV_GANHO_DISTRIBUICAO, "Expectativa de novas listagens em lojas adicionais"),
        (EV_NOVA_LOJA, "Abertura de novas lojas prevista"),
        (EV_ACAO_CONCORRENTE, "Concorrente em ruptura - oportunidade"),
    ]
    pessimistic = [
        (EV_PERDA_CLIENTE, "Cliente reduzindo os níveis de estoque"),
        (EV_ACAO_CONCORRENTE, "Promoção do concorrente prevista"),
        (EV_MUDANCA_PRECO, "Aumento de preço pode reduzir o volume"),
    ]
    for (cust_name, sku), mult in event_mult.items():
        for k, d in enumerate(last12):
            idx = len(months) - 12 + k
            row = keyed.get((cust_name, sku, d))
            if row is None:
                continue
            true_uplift = float(mult[idx] - 1)
            if row["Promotion"] == 1 and r.random() < 0.55:
                adj = true_uplift * r.uniform(0.65, 1.15)
                planner = r.choice([PLANNER_TRADE_MARKETING, PLANNER_DEMAND_PLANNER])
                rows.append(
                    dict(
                        Date=d,
                        Customer=cust_name,
                        SKU=sku,
                        Planner=str(planner),
                        EventType=EV_PROMOCAO,
                        AdjustmentPct=round(adj, 4),
                        Comment=str(r.choice(promo_comments)),
                    )
                )
            elif row["MerchandisingEvent"] == 1 and r.random() < 0.45:
                adj = true_uplift * r.uniform(0.6, 1.2)
                rows.append(
                    dict(
                        Date=d,
                        Customer=cust_name,
                        SKU=sku,
                        Planner=PLANNER_TRADE_MARKETING,
                        EventType=EV_MERCHANDISING,
                        AdjustmentPct=round(adj, 4),
                        Comment=str(r.choice(merch_comments)),
                    )
                )
            elif r.random() < 0.055:
                if r.random() < 0.72:
                    ev, comment = optimistic[int(r.integers(0, len(optimistic)))]
                    adj = r.uniform(0.08, 0.30)
                    planner = r.choice([PLANNER_SALES_DIRECTOR, PLANNER_KAM, PLANNER_MARKETING], p=[0.4, 0.45, 0.15])
                else:
                    ev, comment = pessimistic[int(r.integers(0, len(pessimistic)))]
                    adj = -r.uniform(0.08, 0.22)
                    planner = r.choice([PLANNER_KAM, PLANNER_DEMAND_PLANNER])
                rows.append(
                    dict(
                        Date=d,
                        Customer=cust_name,
                        SKU=sku,
                        Planner=str(planner),
                        EventType=ev,
                        AdjustmentPct=round(adj, 4),
                        Comment=comment,
                    )
                )
    df = pd.DataFrame(rows, columns=["Date", "Customer", "SKU", "Planner", "EventType", "AdjustmentPct", "Comment"])
    return df.sort_values(["Date", "Customer", "SKU"]).reset_index(drop=True)


def _plan(seed: int, sales: pd.DataFrame, months: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    """Orçamento anual e metas de vendas: últimos 12 meses do histórico + horizonte do forecast.

    O orçamento é montado como em muitas empresas: real do ano anterior vezes
    uma premissa de crescimento. Isso embute gaps de S&OP realistas (planos
    otimistas para clientes em queda, crescimento subestimado no e-commerce, ...).
    """
    r = _rng(seed, "plan")
    future = pd.date_range(months[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    plan_months = months[-12:].append(future)
    cust_by_name = {c.name: c for c in CUSTOMERS}
    prod_by_sku = {p.sku: p for p in PRODUCTS}
    pivot = sales.pivot_table(index=["Customer", "SKU"], columns="Date", values="Units", aggfunc="sum")
    price = sales.groupby(["Customer", "SKU"])["Price"].last()
    rows = []
    for (cust_name, sku), hist in pivot.iterrows():
        cust = cust_by_name[cust_name]
        prod = prod_by_sku[sku]
        hist = hist.reindex(months).fillna(0.0)
        recent = hist.iloc[-3:].mean()
        sku_adj = {"trending": 0.02, "declining": -0.02}.get(prod.pattern, 0.0)
        for d in plan_months:
            ly = d - pd.DateOffset(years=1)
            ly_units = float(hist.get(ly, 0.0))
            if prod.pattern == "launch" and ly_units == 0:
                ly_units = float(recent)
            growth = cust.budget_growth + sku_adj + r.normal(0, 0.015)
            budget = max(0.0, ly_units * (1 + growth))
            stretch = cust.target_stretch + r.normal(0, 0.01)
            if prod.pattern == "trending" and cust.target_stretch < 0.1:
                stretch -= 0.03  # metas que ignoram o momentum -> subestimadas
            target = max(0.0, budget * (1 + stretch))
            plan_price = float(price.loc[(cust_name, sku)]) * 1.03
            rows.append(
                dict(
                    Date=d,
                    Customer=cust_name,
                    SKU=sku,
                    BudgetUnits=round(budget),
                    TargetUnits=round(target),
                    BudgetRevenue=round(budget * plan_price, 2),
                    TargetRevenue=round(target * plan_price, 2),
                )
            )
    return pd.DataFrame(rows)


def _future_overrides(months: pd.DatetimeIndex, listing: dict[str, list[Product]]) -> pd.DataFrame:
    """Alguns eventos comerciais pendentes, para que o Consenso seja diferente do forecast base."""
    f = pd.date_range(months[-1] + pd.offsets.MonthBegin(1), periods=12, freq="MS")
    by_code = {c.code: c for c in CUSTOMERS}
    candidates = [
        (
            "C001",
            "SKU-20102",
            f[1],
            EV_PROMOCAO,
            0.35,
            "Tabloide de Black Friday - desconto em Crocantes Batata Queijo",
        ),
        ("C001", "SKU-30102", f[2], EV_MERCHANDISING, 0.15, "Pontas de gôndola de protetor solar em todas as lojas"),
        ("C003", None, f[4], EV_NOVA_LOJA, 0.08, "Abertura de duas novas lojas MaxiCompra (todos os SKUs)"),
        ("C006", "SKU-20202", f[0], EV_CAMPANHA, 0.20, "Campanha digital de NutriBar Proteína"),
        ("C002", "SKU-10201", f[3], EV_PROMOCAO, 0.30, "Promoção de verão de sucos acordada no JBP"),
        ("C012", None, f[6], EV_PERDA_CLIENTE, -0.10, "Cliente reduzindo o sortimento em 3 lojas"),
        ("C008", "SKU-30101", f[7], EV_GANHO_DISTRIBUICAO, 0.12, "Hidratante listado em mais 40 lojas"),
    ]
    rows = []
    for code, sku, d, ev, up, comment in candidates:
        cust = by_code[code]
        if sku is not None and sku not in {p.sku for p in listing[code]}:
            continue
        rows.append(dict(Date=d, Customer=cust.name, SKU=sku, EventType=ev, UpliftPct=up, Comment=comment))
    return pd.DataFrame(rows, columns=["Date", "Customer", "SKU", "EventType", "UpliftPct", "Comment"])


def generate_dataset(
    random_seed: int = 42,
    end_month: str = "2026-09",
    n_months: int = 60,
    horizon: int = 12,
) -> SyntheticDataset:
    """Gera a base de demonstração completa (histórico de vendas, plano, ajustes comerciais)."""
    end = pd.Timestamp(end_month + "-01")
    months = pd.date_range(end=end, periods=n_months, freq="MS")
    cal = [month_features(d.year, d.month) for d in months]
    listing = _assortment(random_seed)

    price_paths: dict[str, tuple[np.ndarray, list[dict]]] = {}
    campaigns: dict[str, np.ndarray] = {}
    for prod in PRODUCTS:
        price_paths[prod.sku] = _sku_price_path(random_seed, prod, n_months, months)
        campaigns[prod.sku] = _sku_campaigns(random_seed, prod, n_months)

    frames: list[pd.DataFrame] = []
    infos: list[dict[str, Any]] = []
    event_mult: dict[tuple[str, str], np.ndarray] = {}
    for cust in CUSTOMERS:
        for prod in listing[cust.code]:
            df, info, em = _simulate_series(
                random_seed, cust, prod, months, price_paths[prod.sku][0], campaigns[prod.sku], cal
            )
            frames.append(df)
            infos.append(info)
            event_mult[(cust.name, prod.sku)] = em

    sales = pd.concat(frames, ignore_index=True)
    cust_by_name = {c.name: c for c in CUSTOMERS}
    prod_by_sku = {p.sku: p for p in PRODUCTS}
    holidays = {d: int(f["holidays"]) for d, f in zip(months, cal, strict=True)}

    # Potencial do cliente = unidades anuais endereçáveis (itens listados + espaço não listado).
    potentials = {}
    for cust in CUSTOMERS:
        r = _rng(random_seed, "potential", cust.code)
        cust_units = sales.loc[sales["Customer"] == cust.name].groupby("Date")["Units"].sum()
        annual = float(cust_units.tail(12).sum())
        potentials[cust.name] = round(annual * r.uniform(1.25, 1.9), -2)

    sales["Region"] = sales["Customer"].map(lambda c: cust_by_name[c].region)
    sales["Channel"] = sales["Customer"].map(lambda c: cust_by_name[c].channel)
    sales["CustomerLocation"] = sales["Customer"].map(lambda c: cust_by_name[c].location)
    sales["CustomerPotential"] = sales["Customer"].map(potentials)
    sales["Product"] = sales["SKU"].map(lambda s: prod_by_sku[s].name)
    sales["Category"] = sales["SKU"].map(lambda s: prod_by_sku[s].category)
    sales["Brand"] = sales["SKU"].map(lambda s: prod_by_sku[s].brand)
    sales["Holiday"] = sales["Date"].map(holidays)
    sales["Revenue"] = (sales["Units"] * sales["Price"]).round(2)
    sales = (
        sales[
            [
                "Date",
                "Region",
                "Channel",
                "Customer",
                "CustomerLocation",
                "CustomerPotential",
                "SKU",
                "Product",
                "Category",
                "Brand",
                "Units",
                "Revenue",
                "Price",
                "Promotion",
                "Distribution",
                "StockOut",
                "Holiday",
                "MarketingInvestment",
                "MerchandisingEvent",
            ]
        ]
        .sort_values(["Customer", "SKU", "Date"])
        .reset_index(drop=True)
    )

    plan = _plan(random_seed, sales, months, horizon)
    hist_ov = _historical_overrides(random_seed, sales, event_mult, months)
    fut_ov = _future_overrides(months, listing)

    metadata = {
        "generator_version": GENERATOR_VERSION,
        "random_seed": random_seed,
        "company": COMPANY,
        "start": months[0].strftime("%Y-%m-%d"),
        "end": months[-1].strftime("%Y-%m-%d"),
        "n_months": n_months,
        "n_series": len(infos),
        "n_rows": len(sales),
        "sku_patterns": {p.sku: PATTERN_LABELS[p.pattern] for p in PRODUCTS},
        "true_price_elasticity": PRICE_ELASTICITY,
        "true_distribution_elasticity": DISTRIBUTION_ELASTICITY,
        "true_marketing_elasticity": MARKETING_ELASTICITY,
        "price_events": {p.sku: price_paths[p.sku][1] for p in PRODUCTS if price_paths[p.sku][1]},
        "store_openings": {c.name: [list(x) for x in c.store_openings] for c in CUSTOMERS if c.store_openings},
        "series_events": [i for i in infos if i["events"]],
        "disclaimer": (
            "Todos os dados são sintéticos e fictícios. Nenhuma empresa, cliente ou produto real está representado."
        ),
    }
    return SyntheticDataset(
        sales=sales, plan=plan, historical_overrides=hist_ov, future_overrides=fut_ov, metadata=metadata
    )
