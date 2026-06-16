"""Drinks ordering — per-week pars scaled to the delivery window.

`par` is the normal per-week usage ("Qnty Needed"). An order covers a delivery WINDOW
(e.g. ~0.9 weeks for a Wed→Sun run), less what's on hand, rounded UP:
    order = max(0, ceil(par * weeks - on_hand))

Items are listed in fridge/count order; the produced order is sorted into the Coca-Cola
(CCEP) "Frequently Ordered" site sequence (seq) so it's quick to add to cart top-to-bottom.
Edit pars/seq per store as the range or usage changes.
"""
import math
import datetime as dt

AU_STATES = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]

# (item, par_per_week, section, seq)
_ITEMS = [
    ("Coke 390ml",              6, "390ml Cans",     2),
    ("Coke Zero 390ml",         7, "390ml Cans",     5),
    ("Diet Coke 390ml",         2, "390ml Cans",     8),
    ("Sprite 390ml",            2, "390ml Cans",    13),
    ("Fanta 390ml",             2, "390ml Cans",    16),
    ("Coke 600ml",              5, "600ml Bottles",  1),
    ("Coke Zero 600ml",         6, "600ml Bottles",  4),
    ("Diet Coke 600ml",         3, "600ml Bottles",  7),
    ("Vanilla Coke Zero 600ml", 2, "600ml Bottles", 11),
    ("Fanta 600ml",             3, "600ml Bottles", 15),
    ("Sprite 600ml",            3, "600ml Bottles", 12),
    ("Sprite Zero 600ml",       2, "600ml Bottles", 14),
    ("Fanta Lemon 600ml",       2, "600ml Bottles", 17),
    ("Pasito 600ml",            2, "600ml Bottles", 20),
    ("Sparkling Water",         2, "600ml Bottles", 24),
    ("Water",                   7, "600ml Bottles", 21),
    ("Peach Fuze Tea",          2, "Fuze Tea",      34),
    ("Lemon Fuze Tea",          2, "Fuze Tea",      33),
    ("Mango Fuze Tea",          2, "Fuze Tea",      35),
    ("Purple Powerade",         2, "Powerade",      29),
    ("Blue Powerade",           2, "Powerade",      26),
    ("Yellow Powerade",         2, "Powerade",      28),
    ("Red Powerade",            2, "Powerade",      27),
    ("Orange Powerade",         2, "Powerade",      30),
    ("Coke 1.25L",              2, "1.25L & 1.5L",   3),
    ("Coke Zero 1.25L",         2, "1.25L & 1.5L",   6),
    ("Water 1.5L",              2, "1.25L & 1.5L",  22),
    ("Apple Juice",             2, "Juice",         32),
    ("Orange Juice",            2, "Juice",         31),
]

# Public list of dicts, in SHEET order (the count grid follows the physical fridge).
DRINK_ITEMS = [{"item": it, "par": par, "section": sec, "seq": seq}
               for (it, par, sec, seq) in _ITEMS]


def default_delivery(today, weekday=1):
    """Next delivery date strictly after today for the given weekday (Mon=0..Sun=6)."""
    ahead = (weekday - today.weekday()) % 7
    return today + dt.timedelta(days=ahead or 7)


def coverage(today, cover_until):
    """(days, weeks) the order must cover — today through cover_until, inclusive.
    weeks = days / 7 since the par is a per-week usage rate."""
    days = max((cover_until - today).days + 1, 1)
    return days, days / 7.0


def order_qty(weekly_use, on_hand, weeks=1.0):
    """Units to order, rounded UP, never negative: ceil(weekly_use * weeks - on_hand)."""
    try:
        oh = float(on_hand or 0)
    except (TypeError, ValueError):
        oh = 0.0
    try:
        wk = float(weeks)
    except (TypeError, ValueError):
        wk = 1.0
    return max(0, math.ceil(float(weekly_use) * wk - oh))


def build_order(counts, weeks=1.0):
    """{item: on_hand} → order list in CCEP site order (by seq), order > 0 only.
    [{"item", "weekly_use", "need", "on_hand", "order", "seq"}, ...]"""
    counts = counts or {}
    out = []
    for row in DRINK_ITEMS:
        weekly_use = row["par"]
        oh = counts.get(row["item"])
        qty = order_qty(weekly_use, oh, weeks)
        if qty <= 0:
            continue
        out.append({"item": row["item"], "weekly_use": weekly_use, "seq": row["seq"],
                    "need": round(float(weekly_use) * float(weeks), 1),
                    "on_hand": float(oh or 0), "order": qty})
    out.sort(key=lambda e: e["seq"])
    return out


def order_text(order_list):
    """Plain-text drinks order — one line per item, in CCEP site order."""
    lines = ["Drinks order", ""]
    if not order_list:
        lines.append("(nothing to order)")
        return "\n".join(lines)
    for e in order_list:
        lines.append(f"{e['order']:g} x {e['item']}")
    return "\n".join(lines)


def public_holidays_within(state, start, days=7):
    """[(date, name)] public holidays in [start, start+days] for an AU state. Returns []
    if the `holidays` package isn't installed (degrades quietly to no PH heads-up)."""
    try:
        import holidays as _holidays
    except Exception:
        return []
    if state not in AU_STATES:
        return []
    end = start + dt.timedelta(days=days)
    try:
        cal = _holidays.Australia(subdiv=state, years=range(start.year, end.year + 1))
    except Exception:
        return []
    return sorted((d, cal.get(d)) for d in cal if start <= d <= end)
