# Menu Margin Analyzer Skill

## Purpose
Estimates gross profit margin for each menu item by summing waste-adjusted ingredient costs and comparing against the selling price. Helps identify low-margin items that may need repricing.

## Data Source
`SNOWFLAKE_LEARNING_DB.ANALYTIC.MENU_MARGIN` view

## Logic
- Joins `MENU_INGREDIENT_TAGS` → `INGREDIENTS` (for waste %) → `VENDOR_OFFERINGS` (cheapest unit price per ingredient)
- Applies waste adjustment: `unit_price / (1 - waste_pct/100)` — this inflates cost to reflect that e.g. 10% of fresh produce is lost to spoilage/human error
- Sums waste-adjusted costs across all tagged ingredients for each menu item
- Calculates: `ESTIMATED_MARGIN_PCT = (menu_price - estimated_cogs) / menu_price × 100`

## Precision Note
We don't have gram-level recipe quantities — only ingredient-to-item associations. The COGS estimate sums full per-unit vendor prices for each tagged ingredient, so absolute values are inflated. Use this for **relative ranking** (which items have worse margins) rather than exact accounting.

## Inputs
- Item name or category (optional filter)
- Business ID

## Example Questions

**"What's my margin on the latte?"**
```sql
SELECT ITEM_NAME, MENU_PRICE, ESTIMATED_COGS, ESTIMATED_MARGIN_PCT
FROM ANALYTIC.MENU_MARGIN
WHERE LOWER(ITEM_NAME) LIKE '%latte%';
```

**"Which menu items have the worst margins?"**
```sql
SELECT ITEM_NAME, MENU_PRICE, ESTIMATED_COGS, ESTIMATED_MARGIN_PCT
FROM ANALYTIC.MENU_MARGIN
WHERE BUSINESS_ID = 'HSC001'
ORDER BY ESTIMATED_MARGIN_PCT ASC LIMIT 10;
```

**"Show margin breakdown for all sushi items"**
```sql
SELECT ITEM_NAME, MENU_PRICE, ESTIMATED_COGS,
       TAGGED_INGREDIENT_COUNT, ESTIMATED_MARGIN_PCT
FROM ANALYTIC.MENU_MARGIN
WHERE ITEM_CATEGORY = 'Sushi'
ORDER BY ESTIMATED_MARGIN_PCT;
```
