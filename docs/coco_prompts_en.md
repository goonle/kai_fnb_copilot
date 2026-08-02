# CoCo CLI Prompts — Semantic View & Cortex Agent Setup

## Step 1 — Create joined views in the ANALYTIC schema

Prompt to CoCo:

```
In the ANALYTIC schema, create the following views:

1. SALES_DETAIL: Join RAW.DAILY_SALES with RAW.ITEMS on item_id to include
   item_name, item_type, and category. Also join ITEMS with RAW.BUSINESSES
   on business_id to include business_name.

2. INGREDIENT_SALES_LINK: Join RAW.MENU_INGREDIENT_TAGS with RAW.DAILY_SALES
   on item_id to calculate, per date and per ingredient, the total quantity
   sold across all menu items tagged with that ingredient. Also join with
   RAW.INGREDIENTS on ingredient_id to include ingredient_name.

3. VENDOR_PRICE_COMPARISON: Join RAW.VENDOR_OFFERINGS with RAW.INGREDIENTS
   on ingredient_id so that ingredient_name, vendor_name, and
   unit_price_number can be compared side by side for the same ingredient.

4. PURCHASE_DETAIL: Join RAW.PURCHASE_LEDGER with RAW.INGREDIENTS on
   ingredient_id to include ingredient_name and category.
```

## Step 2 — Create the Semantic View

Prompt to CoCo:

```
Create a semantic view based on the ANALYTIC.SALES_DETAIL,
ANALYTIC.INGREDIENT_SALES_LINK, ANALYTIC.VENDOR_PRICE_COMPARISON,
ANALYTIC.PURCHASE_DETAIL views, and RAW.BUSINESSES.

Add business-friendly descriptions and synonyms to each column, for example:
- item_name: "Name of the menu or drink item", synonyms "menu", "dish"
- revenue_number: "Actual realized sales revenue after discounts are applied",
  synonyms "revenue", "sales"
- ingredient_name: "Name of the raw ingredient", synonyms "ingredient",
  "raw material"
- unit_price_number: "Purchase price per unit from the vendor", synonyms
  "price", "unit cost"
- discount_rate: "Discount rate applied to the sale", synonyms "discount",
  "markdown"
- business_name: "Name of the business/store", synonyms "cafe",
  "restaurant"

Clearly define the relationships between the tables, using business_id as
the key that links records back to a specific business.
```

## Step 3 — Review the output (this is the human's job)

After CoCo generates the definition, check especially:
- Is `revenue_number` clearly described as "net of discount," so the agent
  doesn't confuse it with list-price revenue?
- Does `INGREDIENT_SALES_LINK` correctly reflect the fact that one
  ingredient can map to many menu items (1:N)? This directly affects the
  accuracy of salmon-related questions.

If something looks wrong, correct it conversationally, e.g.:

```
The description for revenue_number should explicitly say "this figure
already has any discount applied — it is not the list price." Please
update it.
```

## Step 4 — Create the Cortex Agent

Prompt to CoCo:

```
Create a Cortex Agent named FOOD_INTEL_AGENT. Use the semantic view you
just created as its primary data source. When answering, always show the
SQL query that was used to generate the answer.
```

## Step 5 — Test questions (at least 8)

```
1. "How many salmon-related menu items were sold this month in total?"
2. "Compare the trend of salmon purchase volume against the trend of
   salmon-related menu item sales."
3. "Which vendor sells Fresh Salmon Fillet at the lowest price?"
4. "How much does the price of Chicken Breast vary across vendors?"
5. "Which items were sold at a discount this week, and what was the total
   discount loss?"
6. "What are the top 5 best-selling menu items?"
7. "Which business had higher revenue this month, Harbour Street Cafe or
   Nonna's Trattoria?"
   (Note: before RBAC is applied, both businesses' data should be visible.
   After RBAC is applied, only one business's data should show up depending
   on the role — use this difference later in the RBAC demo.)
8. "How much did we purchase from Nishi Asian Foods NZ this month in
   total?"
```
