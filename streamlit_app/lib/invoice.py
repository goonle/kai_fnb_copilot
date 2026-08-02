"""
Purchase invoice save pipeline.

Flow for each line item extracted from an invoice:
  1. Resolve INGREDIENT_ID — exact match, fuzzy match, or create new.
  2. Upsert VENDOR_OFFERINGS (PK = vendor_name + ingredient_id).
  3. Insert PURCHASE_LEDGER row referencing the resolved ingredient_id.

Add this to your app.py / a shared db_helpers.py file.
"""

import difflib


# ---------------------------------------------------------------------------
# 1. Ingredient matching / creation
# ---------------------------------------------------------------------------

def fetch_ingredient_lookup(cur) -> dict:
    """
    Returns {INGREDIENT_NAME_UPPER: INGREDIENT_ID} for all existing ingredients.
    Call once per save operation (not per row) to avoid repeated round trips.
    """
    cur.execute("SELECT INGREDIENT_ID, INGREDIENT_NAME FROM RAW.INGREDIENTS")
    return {name.upper(): ing_id for ing_id, name in cur.fetchall()}


def match_ingredient(name: str, lookup: dict, cutoff: float = 0.82) -> tuple[str | None, str | None]:
    """
    Try to resolve `name` against existing ingredients.
    Returns (ingredient_id, matched_name) if found (exact or fuzzy),
    or (None, None) if no confident match exists — caller should create new.
    """
    upper_name = name.strip().upper()

    # Exact match first
    if upper_name in lookup:
        return lookup[upper_name], upper_name

    # Fuzzy match — only accept if reasonably confident
    close = difflib.get_close_matches(upper_name, lookup.keys(), n=1, cutoff=cutoff)
    if close:
        return lookup[close[0]], close[0]

    return None, None


def generate_next_ingredient_id(cur, prefix: str = "ING") -> str:
    """
    Generates the next sequential ingredient ID, e.g. ING001, ING002, ...
    Assumes existing IDs follow the same prefix pattern.
    """
    cur.execute(
        "SELECT INGREDIENT_ID FROM RAW.INGREDIENTS WHERE INGREDIENT_ID LIKE %s",
        (f"{prefix}%",),
    )
    existing = [row[0] for row in cur.fetchall()]
    max_num = 0
    for ing_id in existing:
        suffix = ing_id[len(prefix):]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"{prefix}{max_num + 1:03d}"


def create_ingredient(cur, name: str, unit: str, category: str | None = None) -> str:
    """
    Inserts a new ingredient and returns its generated INGREDIENT_ID.
    """
    new_id = generate_next_ingredient_id(cur)
    cur.execute(
        """
        INSERT INTO RAW.INGREDIENTS (INGREDIENT_ID, INGREDIENT_NAME, CATEGORY, STANDARD_UNIT)
        VALUES (%s, %s, %s, %s)
        """,
        (new_id, name.strip(), category, unit),
    )
    return new_id


def resolve_ingredient(cur, lookup: dict, name: str, unit: str,
                        category: str | None = None) -> tuple[str, bool]:
    """
    Resolves an ingredient name to an ID, creating it if necessary.
    Returns (ingredient_id, was_created).
    Also updates `lookup` in place so subsequent rows in the same batch
    can reuse a newly created ingredient instead of creating duplicates.
    """
    ing_id, matched_name = match_ingredient(name, lookup)
    if ing_id:
        return ing_id, False

    new_id = create_ingredient(cur, name, unit, category)
    lookup[name.strip().upper()] = new_id
    return new_id, True


# ---------------------------------------------------------------------------
# 2. Vendor name matching
# ---------------------------------------------------------------------------

def fetch_vendor_lookup(cur) -> dict:
    """
    Returns {VENDOR_NAME_UPPER: VENDOR_NAME} for all vendors seen so far
    (distinct across VENDOR_OFFERINGS and PURCHASE_LEDGER, since there's no
    separate vendor master table — vendor is free text).
    """
    cur.execute(
        """
        SELECT DISTINCT VENDOR_NAME FROM RAW.VENDOR_OFFERINGS
        UNION
        SELECT DISTINCT VENDOR FROM RAW.PURCHASE_LEDGER
        """
    )
    return {name.strip().upper(): name for (name,) in cur.fetchall() if name}


def match_vendor(name: str, lookup: dict, cutoff: float = 0.82) -> str:
    """
    Resolves `name` against vendors already seen. Returns the existing
    canonical spelling on an exact or fuzzy match, otherwise returns `name`
    as-is (vendor is free text, so an unmatched name just becomes new).
    """
    upper_name = name.strip().upper()

    if upper_name in lookup:
        return lookup[upper_name]

    close = difflib.get_close_matches(upper_name, lookup.keys(), n=1, cutoff=cutoff)
    if close:
        return lookup[close[0]]

    return name.strip()


# ---------------------------------------------------------------------------
# 3. Vendor offerings upsert
# ---------------------------------------------------------------------------

def upsert_vendor_offering(cur, vendor_name: str, ingredient_id: str,
                            purchase_unit: str, pack_size: float,
                            price_number: float, price_unit: str = "NZD"):
    """
    MERGE into VENDOR_OFFERINGS since (VENDOR_NAME, INGREDIENT_ID) is the PK.
    Keeps the latest observed price/pack info for this vendor+ingredient pair.
    """
    cur.execute(
        """
        MERGE INTO RAW.VENDOR_OFFERINGS AS target
        USING (SELECT %s AS VENDOR_NAME, %s AS INGREDIENT_ID) AS source
        ON target.VENDOR_NAME = source.VENDOR_NAME
           AND target.INGREDIENT_ID = source.INGREDIENT_ID
        WHEN MATCHED THEN UPDATE SET
            PURCHASE_UNIT = %s,
            PACK_SIZE = %s,
            PRICE_NUMBER = %s,
            PRICE_UNIT = %s
        WHEN NOT MATCHED THEN INSERT
            (VENDOR_NAME, INGREDIENT_ID, PURCHASE_UNIT, PACK_SIZE, PRICE_NUMBER, PRICE_UNIT)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            vendor_name, ingredient_id,                                   # ON
            purchase_unit, pack_size, price_number, price_unit,           # UPDATE
            vendor_name, ingredient_id, purchase_unit, pack_size,         # INSERT
            price_number, price_unit,
        ),
    )


# ---------------------------------------------------------------------------
# 4. Purchase ledger insert
# ---------------------------------------------------------------------------

def insert_purchase_ledger_row(cur, business_id: str, week_start: str, vendor: str,
                                ingredient: str, ingredient_id: str,
                                qty_packs: float, pack_size: float, unit: str,
                                unit_price_number: float, unit_price_unit: str = "NZD"):
    line_total_number = round(qty_packs * unit_price_number, 2)
    cur.execute(
        """
        INSERT INTO RAW.PURCHASE_LEDGER (
            BUSINESS_ID, WEEK_START, VENDOR, INGREDIENT, INGREDIENT_ID,
            QTY_PACKS, PACK_SIZE, UNIT,
            UNIT_PRICE_NUMBER, UNIT_PRICE_UNIT,
            LINE_TOTAL_NUMBER, LINE_TOTAL_UNIT
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            business_id, week_start, vendor, ingredient, ingredient_id,
            qty_packs, pack_size, unit,
            unit_price_number, unit_price_unit,
            line_total_number, unit_price_unit,
        ),
    )


# ---------------------------------------------------------------------------
# 5. Orchestrator — call this from the Streamlit "Save" button
# ---------------------------------------------------------------------------

def save_purchase_invoice(cur, business_id: str, vendor: str, week_start: str,
                           items: list[dict]) -> dict:
    """
    items: list of dicts with keys ingredient, qty_packs, pack_size, unit, unit_price
    Returns a summary dict for UI feedback:
    {"created_ingredients": [...], "rows_saved": N, "vendor": "<resolved name>"}
    """
    ingredient_lookup = fetch_ingredient_lookup(cur)
    vendor = match_vendor(vendor, fetch_vendor_lookup(cur))
    created_ingredients = []

    for item in items:
        ingredient_name = item["ingredient"]
        unit = item.get("unit") or "ea"
        pack_size = item.get("pack_size") or 1
        qty_packs = item["qty_packs"]
        unit_price = item.get("unit_price") or 0.0
        category = item.get("category") or None

        ingredient_id, was_created = resolve_ingredient(cur, ingredient_lookup, ingredient_name, unit, category)
        if was_created:
            created_ingredients.append(ingredient_name)

        upsert_vendor_offering(
            cur, vendor, ingredient_id,
            purchase_unit=unit, pack_size=pack_size,
            price_number=unit_price, price_unit="NZD",
        )

        insert_purchase_ledger_row(
            cur, business_id, week_start, vendor,
            ingredient_name, ingredient_id,
            qty_packs, pack_size, unit,
            unit_price, "NZD",
        )

    return {"created_ingredients": created_ingredients, "rows_saved": len(items), "vendor": vendor}
