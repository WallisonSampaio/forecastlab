"""Deterministic natural-language helpers (EN / PT-BR) and number formatting."""

from __future__ import annotations

import math

MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTHS_PT = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def money(v: float | None, lang: str = "en") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        s = f"{a / 1e9:.2f}B"
    elif a >= 1e6:
        s = f"{a / 1e6:.2f}M"
    elif a >= 1e3:
        s = f"{a / 1e3:.1f}K"
    else:
        s = f"{a:.0f}"
    if lang == "pt":
        s = s.replace("B", " bi").replace("M", " mi").replace("K", " mil").replace(".", ",")
    return f"{sign}R$ {s}"


def units(v: float | None, lang: str = "en") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e6:
        s = f"{a / 1e6:.2f}M"
    elif a >= 1e3:
        s = f"{a / 1e3:.1f}K"
    else:
        s = f"{a:.0f}"
    if lang == "pt":
        s = s.replace("M", " mi").replace("K", " mil").replace(".", ",")
    return f"{sign}{s} {'un.' if lang == 'pt' else 'units'}"


def measure(v: float | None, m: str, lang: str = "en") -> str:
    return money(v, lang) if m == "revenue" else units(v, lang)


def pct(v: float | None, lang: str = "en", signed: bool = False, digits: int = 1) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    s = f"{v * 100:+.{digits}f}%" if signed else f"{v * 100:.{digits}f}%"
    return s.replace(".", ",") if lang == "pt" else s


def month_name(date_str: str, lang: str = "en") -> str:
    y, m = int(date_str[:4]), int(date_str[5:7])
    return f"{MONTHS_PT[m - 1]}/{y}" if lang == "pt" else f"{MONTHS_EN[m - 1]} {y}"


def t(lang: str, en: str, pt: str) -> str:
    return pt if lang == "pt" else en


CLASS_LABEL = {
    "REALISTIC": ("REALISTIC", "REALISTA"),
    "STRETCH": ("STRETCH", "DESAFIADORA"),
    "AGGRESSIVE": ("AGGRESSIVE", "AGRESSIVA"),
    "UNDERESTIMATED": ("UNDERESTIMATED", "SUBESTIMADA"),
}


def class_label(cls: str, lang: str) -> str:
    en, pt_ = CLASS_LABEL.get(cls, (cls, cls))
    return pt_ if lang == "pt" else en
