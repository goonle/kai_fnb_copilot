# Supplier Optimizer Skill

## Purpose
Identifies cost-saving opportunities by ranking vendors for each ingredient and calculating potential monthly savings from switching to cheaper suppliers.

## Data Source
`SNOWFLAKE_LEARNING_DB.ANALYTIC.SUPPLIER_OPTIMIZER` view

## Logic
- Pulls all vendor×ingredient price combinations from `VENDOR_OFFERINGS`
- Ranks each vendor by `PRICE_NUMBER` (lowest = rank 1) per ingredient
- Identifies the most-recent vendor from `PURCHASE_LEDGER` as the "current" supplier
- Estimates monthly purchase volume (avg weekly packs × 4) from purchase history
- Calculates savings: `(current_price - cheapest_price) × est_monthly_packs`
- Only includes ingredients with 2+ vendors on record

## Inputs
- Ingredient name (optional filter)
- Business ID (for purchase history context)

## Example Questions

**"Which supplier should I switch to for salmon?"**
```sql
SELECT INGREDIENT_NAME, CURRENT_VENDOR, CURRENT_PRICE,
       CHEAPEST_VENDOR, CHEAPEST_PRICE, EST_MONTHLY_SAVINGS_NZD
FROM ANALYTIC.SUPPLIER_OPTIMIZER
WHERE LOWER(INGREDIENT_NAME) LIKE '%salmon%' AND PRICE_RANK = 1;
```

**"What are my top 5 biggest cost-saving opportunities?"**
```sql
SELECT INGREDIENT_NAME, CURRENT_VENDOR, CHEAPEST_VENDOR,
       CHEAPEST_PRICE, EST_MONTHLY_SAVINGS_NZD
FROM ANALYTIC.SUPPLIER_OPTIMIZER
WHERE PRICE_RANK = 1 AND EST_MONTHLY_SAVINGS_NZD > 0
ORDER BY EST_MONTHLY_SAVINGS_NZD DESC LIMIT 5;
```

**"Show all vendors for chicken breast ranked by price"**
```sql
SELECT VENDOR_NAME, PRICE_NUMBER, PURCHASE_UNIT, PRICE_RANK
FROM ANALYTIC.SUPPLIER_OPTIMIZER
WHERE LOWER(INGREDIENT_NAME) LIKE '%chicken breast%'
ORDER BY PRICE_RANK;
```
