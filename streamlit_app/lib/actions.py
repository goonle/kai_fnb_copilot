"""
Database write-back actions.
Turns AI recommendations into real changes in Snowflake tables.
"""


def generate_alert_id(cur) -> str:
    """Generate next sequential alert ID like ALT001, ALT002, etc."""
    cur.execute("SELECT ALERT_ID FROM RAW.PRICE_ALERTS WHERE ALERT_ID LIKE 'ALT%' ORDER BY ALERT_ID DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        num = int(row[0][3:]) + 1
    else:
        num = 1
    return f"ALT{num:03d}"


def record_alert(cur, business_id: str, alert: dict) -> str:
    """
    Insert a price alert record. Returns the generated ALERT_ID.
    alert dict keys: ingredient_id, ingredient, old_price, new_price, change_pct,
                     alternative_vendor, alternative_price, est_monthly_impact, vendor
    """
    alert_id = generate_alert_id(cur)
    cur.execute(
        """
        INSERT INTO RAW.PRICE_ALERTS (
            ALERT_ID, BUSINESS_ID, INGREDIENT_ID, INGREDIENT_NAME, VENDOR_NAME,
            OLD_PRICE_NUMBER, NEW_PRICE_NUMBER, CHANGE_PCT,
            ALTERNATIVE_VENDOR, ALTERNATIVE_PRICE, EST_MONTHLY_IMPACT, STATUS
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """,
        (
            alert_id, business_id,
            alert.get("ingredient_id"), alert.get("ingredient"), alert.get("vendor", ""),
            alert.get("old_price"), alert.get("new_price"),
            round(alert.get("change_pct", 0) * 100, 2),
            alert.get("alternative_vendor"), alert.get("alternative_price"),
            alert.get("est_monthly_impact"),
        ),
    )
    return alert_id


def mark_alert_acted(cur, alert_id: str, action_taken: str = "acted"):
    """Update alert status to 'acted' or 'acknowledged'."""
    cur.execute(
        "UPDATE RAW.PRICE_ALERTS SET STATUS = %s WHERE ALERT_ID = %s",
        (action_taken, alert_id),
    )


def update_menu_price(cur, item_id: str, new_price: float):
    """Update the selling price of a menu item."""
    cur.execute(
        "UPDATE RAW.ITEMS SET PRICE_NUMBER = %s WHERE ITEM_ID = %s",
        (round(new_price, 2), item_id),
    )


def update_waste_pct(cur, ingredient_id: str, waste_pct: float):
    """
    Update the waste percentage for an ingredient.
    waste_pct should be a number like 8.0 for 8%.
    """
    cur.execute(
        "UPDATE RAW.INGREDIENTS SET WASTE_PCT = %s WHERE INGREDIENT_ID = %s",
        (round(waste_pct, 2), ingredient_id),
    )


def get_affected_menu_items(cur, business_id: str, ingredient_id: str) -> list[dict]:
    """Find menu items that use this ingredient (via MENU_INGREDIENT_TAGS)."""
    cur.execute(
        """
        SELECT i.ITEM_ID, i.ITEM_NAME, i.PRICE_NUMBER
        FROM RAW.MENU_INGREDIENT_TAGS mt
        JOIN RAW.ITEMS i ON mt.ITEM_ID = i.ITEM_ID
        WHERE mt.BUSINESS_ID = %s AND mt.INGREDIENT_ID = %s
        """,
        (business_id, ingredient_id),
    )
    return [{"item_id": r[0], "item_name": r[1], "current_price": float(r[2])} for r in cur.fetchall()]


def suggest_price_adjustment(cur, business_id: str, ingredient_id: str, price_increase_pct: float) -> list[dict]:
    """
    For each menu item using this ingredient, suggest a new price that
    absorbs the ingredient cost increase proportionally.
    Factors in waste_pct from the ingredient.
    """
    cur.execute(
        "SELECT WASTE_PCT FROM RAW.INGREDIENTS WHERE INGREDIENT_ID = %s",
        (ingredient_id,),
    )
    row = cur.fetchone()
    waste_pct = float(row[0]) / 100.0 if row and row[0] else 0.05

    items = get_affected_menu_items(cur, business_id, ingredient_id)

    cogs_ratio = 0.35
    avg_ingredients_per_item = 5
    effective_increase = price_increase_pct * (1 + waste_pct) * cogs_ratio / avg_ingredients_per_item

    suggestions = []
    for item in items:
        new_price = round(item["current_price"] * (1 + effective_increase), 2)
        suggestions.append({
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "current_price": item["current_price"],
            "suggested_price": new_price,
            "increase_amount": round(new_price - item["current_price"], 2),
        })

    return suggestions
