"""Calendário do varejo brasileiro (feriados e datas comerciais)."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Domingo de Páscoa gregoriano (algoritmo gregoriano anônimo)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def national_holidays(year: int) -> tuple[date, ...]:
    """Feriados nacionais (mais Carnaval e Corpus Christi, amplamente observados)."""
    e = easter(year)
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    days = [date(year, m, d) for m, d in fixed]
    if year >= 2024:
        days.append(date(year, 11, 20))  # Consciência Negra virou feriado nacional em 2024
    days += [
        e - timedelta(days=48),  # segunda-feira de Carnaval
        e - timedelta(days=47),  # terça-feira de Carnaval
        e - timedelta(days=2),  # Sexta-feira Santa
        e + timedelta(days=60),  # Corpus Christi
    ]
    return tuple(sorted(days))


def carnaval_month(year: int) -> int:
    return (easter(year) - timedelta(days=47)).month


def month_features(year: int, month: int) -> dict[str, int | bool]:
    holidays = sum(1 for d in national_holidays(year) if d.month == month)
    return {
        "holidays": holidays,
        "carnaval": carnaval_month(year) == month,
        "black_friday": month == 11,
        "christmas": month == 12,
        "mothers_day": month == 5,
        "summer": month in (12, 1, 2),
        "winter": month in (6, 7, 8),
    }
