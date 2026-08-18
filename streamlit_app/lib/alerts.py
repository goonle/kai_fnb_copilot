"""
Proactive price-change alerts.
Runs after invoice data is extracted to detect price increases and suggest alternatives.
"""


def detect_price_changes(cur, business_id: str, vendor: str, items: list[dict], threshold: float = 0.05) -> list[dict]:
    """
    Compare each extracted line item's unit_price against the last known price
    in VENDOR_OFFERINGS for the same vendor+ingredient.
    
    Returns a list of alert dicts for items where price increased > threshold (default 5%).
    """
    cur.execute(
        """
        SELECT vo.INGREDIENT_ID, i.INGREDIENT_NAME, vo.UNIT_PRICE_NUMBER, vo.PURCHASE_UNIT
        FROM RAW.VENDOR_OFFERINGS vo
        JOIN RAW.INGREDIENTS i ON vo.INGREDIENT_ID = i.INGREDIENT_ID
        WHERE UPPER(vo.VENDOR_NAME) = UPPER(%s)
        """,
        (vendor,),
    )
    current_prices = {
        row[1].strip().upper(): {"ingredient_id": row[0], "price": float(row[2]), "unit": row[3]}
        for row in cur.fetchall()
    }

    alerts = []
    for item in items:
        ingredient_name = item.get("ingredient", "").strip().upper()
        new_price = item.get("unit_price") or 0.0

        if ingredient_name not in current_prices or new_price <= 0:
            continue

        old_price = current_prices[ingredient_name]["price"]
        if old_price <= 0:
            continue

        change_pct = (new_price - old_price) / old_price

        if change_pct > threshold:
            ingredient_id = current_prices[ingredient_name]["ingredient_id"]
            alt_vendor, alt_price = find_cheapest_alternative(cur, ingredient_id, vendor)
            est_monthly_qty = estimate_monthly_qty(cur, business_id, ingredient_id)
            est_monthly_impact = (new_price - old_price) * est_monthly_qty

            alerts.append({
                "ingredient": item.get("ingredient", ""),
                "ingredient_id": ingredient_id,
                "old_price": old_price,
                "new_price": new_price,
                "change_pct": round(change_pct, 4),
                "unit": current_prices[ingredient_name]["unit"],
                "vendor": vendor,
                "alternative_vendor": alt_vendor,
                "alternative_price": alt_price,
                "est_monthly_impact": round(est_monthly_impact, 2),
            })

    return alerts


def find_cheapest_alternative(cur, ingredient_id: str, exclude_vendor: str):
    """Find the cheapest vendor for this ingredient, excluding the current one."""
    cur.execute(
        """
        SELECT VENDOR_NAME, UNIT_PRICE_NUMBER
        FROM RAW.VENDOR_OFFERINGS
        WHERE INGREDIENT_ID = %s AND UPPER(VENDOR_NAME) != UPPER(%s)
        ORDER BY UNIT_PRICE_NUMBER ASC
        LIMIT 1
        """,
        (ingredient_id, exclude_vendor),
    )
    row = cur.fetchone()
    return (row[0], float(row[1])) if row else (None, None)


def estimate_monthly_qty(cur, business_id: str, ingredient_id: str) -> float:
    """Estimate monthly purchase quantity based on recent history (avg packs/week * 4)."""
    cur.execute(
        """
        SELECT AVG(weekly_qty) * 4 AS monthly_qty
        FROM (
            SELECT WEEK_START, SUM(QTY_PACKS) AS weekly_qty
            FROM RAW.PURCHASE_LEDGER
            WHERE BUSINESS_ID = %s AND INGREDIENT_ID = %s
            GROUP BY WEEK_START
            ORDER BY WEEK_START DESC
            LIMIT 8
        )
        """,
        (business_id, ingredient_id),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else 4.0
