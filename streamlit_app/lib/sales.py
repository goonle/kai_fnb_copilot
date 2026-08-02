"""
Daily sales (cash-up) report save pipeline.

Flow for each line item extracted from a sales report:
  1. Resolve ITEM_ID by matching item_name against RAW.ITEMS for this business
     (exact or fuzzy match only — unmatched items are skipped rather than
     auto-created, since ITEMS requires a deliberate ITEM_TYPE/CATEGORY/PRICE
     that can't be inferred reliably from a cash-up line).
  2. Insert one DAILY_SALES row per matched item.

Add this to your app.py Sales Report tab's Save button.
"""

import difflib


# ---------------------------------------------------------------------------
# 1. Item matching
# ---------------------------------------------------------------------------

def fetch_item_lookup(cur, business_id: str) -> dict:
    """
    Returns {ITEM_NAME_UPPER: ITEM_ID} for all items belonging to this business.
    """
    cur.execute(
        "SELECT ITEM_ID, ITEM_NAME FROM RAW.ITEMS WHERE BUSINESS_ID = %s",
        (business_id,),
    )
    return {name.strip().upper(): item_id for item_id, name in cur.fetchall()}


def match_item(name: str, lookup: dict, cutoff: float = 0.82) -> str | None:
    """
    Resolves `name` against existing items for this business.
    Returns ITEM_ID if found (exact or fuzzy), or None if no confident match.
    """
    upper_name = name.strip().upper()

    if upper_name in lookup:
        return lookup[upper_name]

    close = difflib.get_close_matches(upper_name, lookup.keys(), n=1, cutoff=cutoff)
    return lookup[close[0]] if close else None


# ---------------------------------------------------------------------------
# 2. Daily sales insert
# ---------------------------------------------------------------------------

def insert_daily_sales_row(cur, business_id: str, sale_date: str, item_id: str,
                            qty_sold: float, revenue: float, revenue_unit: str = "NZD"):
    """
    Cash-up reports only give qty sold + revenue per item, with no
    full-price/discounted split, so QTY_SOLD_FULL_PRICE takes the whole
    qty and DISCOUNT_RATE/QTY_SOLD_DISCOUNTED are left at 0.
    """
    unit_price = round(revenue / qty_sold, 2) if qty_sold else None
    cur.execute(
        """
        INSERT INTO RAW.DAILY_SALES (
            BUSINESS_ID, SALE_DATE, ITEM_ID,
            QTY_SOLD_FULL_PRICE, QTY_SOLD_DISCOUNTED, DISCOUNT_RATE,
            UNIT_PRICE_NUMBER, UNIT_PRICE_UNIT,
            REVENUE_NUMBER, REVENUE_UNIT
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            business_id, sale_date, item_id,
            qty_sold, 0, 0,
            unit_price, revenue_unit,
            revenue, revenue_unit,
        ),
    )


# ---------------------------------------------------------------------------
# 3. Orchestrator — call this from the Streamlit "Save" button
# ---------------------------------------------------------------------------

def save_daily_sales(cur, business_id: str, sale_date: str, items: list[dict]) -> dict:
    """
    items: list of dicts with keys item_name, qty_sold, revenue
    Returns a summary dict for UI feedback:
    {"rows_saved": N, "skipped_items": [...]}
    """
    lookup = fetch_item_lookup(cur, business_id)
    skipped_items = []
    rows_saved = 0

    for item in items:
        item_name = item["item_name"]
        qty_sold = item.get("qty_sold") or 0
        revenue = item.get("revenue") or 0.0

        item_id = match_item(item_name, lookup)
        if not item_id:
            skipped_items.append(item_name)
            continue

        insert_daily_sales_row(cur, business_id, sale_date, item_id, qty_sold, revenue)
        rows_saved += 1

    return {"rows_saved": rows_saved, "skipped_items": skipped_items}
