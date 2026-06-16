"""COGS calculations for a period (month or ISO week).

Revenue comes from the daily-takings slips (pos_days): ex-GST takings, after netting
the delivery-platform commission. COGS comes from invoices (ex-GST), counting only
categories flagged is_cogs (so packaging/cleaning are tracked but excluded from the %).
"""
import json
import pandas as pd
import config

UNIT_MAP = {
    "each": "ea", "unit": "ea", "units": "ea", "ea.": "ea",
    "ctn": "carton", "ctns": "carton", "cartons": "carton",
    "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "boxes": "box", "cases": "case", "trays": "tray",
    "bags": "bag", "litres": "litre", "l": "litre", "doz": "dozen", "tubs": "tub",
}


def norm_unit(u):
    if u is None or (isinstance(u, float) and pd.isna(u)):
        return None
    s = str(u).strip().lower()
    return UNIT_MAP.get(s, s) if s else None


def explode_lines(df: pd.DataFrame) -> pd.DataFrame:
    """One row per invoice line, with supplier/period carried down + a detected tub_type."""
    recs = []
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            raw = r.get("line_items")
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                items = json.loads(raw)
            except Exception:
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                recs.append({
                    "supplier": r["supplier"], "invoice_date": r.get("invoice_date"),
                    "iso_week": r["iso_week"], "month": r["month"],
                    "description": it.get("description"),
                    "quantity": it.get("quantity"),
                    "unit": norm_unit(it.get("unit")),
                    "unit_price": it.get("unit_price"),
                    "amount": it.get("amount"),
                    # stored override (from the Add-invoice tub editor) else detect from text
                    "tub_type": it.get("tub_type") or config.tub_type(it.get("description")),
                })
    cols = ["supplier", "invoice_date", "iso_week", "month", "description",
            "quantity", "unit", "unit_price", "amount", "tub_type"]
    return pd.DataFrame(recs, columns=cols)


def spend_and_deliveries(df, period_col, period_key):
    """(spend $ ex-GST per supplier, #invoices per supplier) for one period."""
    if df is None or df.empty or period_col not in df:
        return pd.Series(dtype=float), pd.Series(dtype=int)
    sub = df[df[period_col] == period_key]
    return sub.groupby("supplier")["total_ex_gst"].sum(), sub.groupby("supplier").size()


def qty_by_supplier_unit(lines, period_col, period_key):
    """{supplier: {unit: {'qty':, 'amount':, 'per_unit':}}} for one period."""
    out = {}
    if lines is None or lines.empty:
        return out
    sub = lines[(lines[period_col] == period_key)
                & lines["quantity"].notna() & lines["unit"].notna()]
    for (sup, unit), g in sub.groupby(["supplier", "unit"]):
        q = float(pd.to_numeric(g["quantity"], errors="coerce").fillna(0).sum())
        amt = float(pd.to_numeric(g["amount"], errors="coerce").fillna(0).sum())
        out.setdefault(sup, {})[unit] = {"qty": q, "amount": amt,
                                         "per_unit": (amt / q if q else None)}
    return out


def fmt_qty(um):
    if not um:
        return "—"
    return " · ".join(f"{d['qty']:g} {u}" for u, d in sorted(um.items(), key=lambda kv: -kv[1]["qty"]))


def baida_tubs(lines, period_col, period_key):
    """Tub + chicken counts for the Baida (chicken) category in one period. Quantity =
    individual chickens, so tubs = chickens / per_tub. Also returns the invoice 'TUB DEPOSIT'
    count as a sanity check.
    {'RSPCA':{'tubs','chickens'}, 'Split':{...}, 'total_tubs','total_chickens','tub_deposit'}"""
    out = {t: {"tubs": 0.0, "chickens": 0.0} for t in config.TUB_TYPES}
    deposit = 0.0
    if lines is not None and not lines.empty:
        sub = lines[(lines["supplier"] == config.BAIDA_SUPPLIER)
                    & (lines[period_col] == period_key)]
        for t, cfg in config.TUB_TYPES.items():
            chickens = float(pd.to_numeric(sub[sub["tub_type"] == t]["quantity"],
                                           errors="coerce").fillna(0).sum())
            out[t] = {"chickens": chickens,
                      "tubs": chickens / cfg["per_tub"] if cfg["per_tub"] else 0.0}
        dep = sub[sub["description"].astype(str).str.lower()
                  .str.contains(config.DEPOSIT_KEYWORD, na=False)]
        deposit = float(pd.to_numeric(dep["quantity"], errors="coerce").fillna(0).sum())
    out["total_tubs"] = sum(out[t]["tubs"] for t in config.TUB_TYPES)
    out["total_chickens"] = sum(out[t]["chickens"] for t in config.TUB_TYPES)
    out["tub_deposit"] = deposit
    return out


def period_col(mode: str) -> str:
    """Which invoice/pos column to group on for the chosen view."""
    return "iso_week" if mode == "week" else "month"


def revenue_for(pos_df: pd.DataFrame, mode: str, period_key: str) -> float:
    """Ex-GST takings for the period (sum of daily adjusted_ex_gst)."""
    if pos_df is None or pos_df.empty:
        return 0.0
    col = period_col(mode)
    if col not in pos_df:
        return 0.0
    return float(pos_df.loc[pos_df[col] == period_key, "adjusted_ex_gst"].sum())


def spend_by_supplier(inv_df: pd.DataFrame, mode: str, period_key: str) -> pd.Series:
    """Ex-GST invoice spend per supplier category for the period."""
    if inv_df is None or inv_df.empty:
        return pd.Series(dtype=float)
    col = period_col(mode)
    if col not in inv_df:
        return pd.Series(dtype=float)
    sub = inv_df[inv_df[col] == period_key]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby("supplier")["total_ex_gst"].sum().sort_values(ascending=False)


def cogs_summary(inv_df, pos_df, mode, period_key) -> dict:
    """Headline figures for the period:
      revenue_ex, cogs_ex (food only), cogs_pct, non_cogs_ex (packaging etc.),
      by_supplier (Series), status ('green'|'amber'|'red')."""
    revenue_ex = revenue_for(pos_df, mode, period_key)
    by_supplier = spend_by_supplier(inv_df, mode, period_key)
    cogs_ex = sum(v for s, v in by_supplier.items() if config.is_cogs(s))
    non_cogs_ex = float(by_supplier.sum()) - cogs_ex
    cogs_pct = (cogs_ex / revenue_ex) if revenue_ex > 0 else 0.0
    return {
        "revenue_ex": revenue_ex,
        "cogs_ex": cogs_ex,
        "non_cogs_ex": non_cogs_ex,
        "cogs_pct": cogs_pct,
        "by_supplier": by_supplier,
        "status": config.total_status(cogs_pct) if revenue_ex > 0 else None,
    }


def period_keys(inv_df, pos_df, mode) -> list:
    """All period keys present in either dataset, newest first."""
    col = period_col(mode)
    keys = set()
    for df in (inv_df, pos_df):
        if df is not None and not df.empty and col in df:
            keys.update(df[col].dropna().unique().tolist())
    return sorted(keys, reverse=True)
