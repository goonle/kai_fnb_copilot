# Dataset — Harbour Street Cafe / Nonna's Trattoria (Multi-Tenant Mock Data)

⚠️ **All data in this folder is synthetic.** Some real NZ wholesale food
vendor names (Bidfood NZ, Gilmours, Service Foods, Trents Wholesale,
Moore Wilson's, South Pacific Seafoods NZ) are used for catalogue-style
realism only — none of these documents were issued by the named companies.
"Nishi Asian Foods NZ" and "Ocean Fresh Direct NZ" are entirely fictional
vendors. All prices, quantities, and transactions are fictional.

## Why two businesses

To demonstrate real row-level, multi-tenant isolation (not just a design
claim), the dataset includes two independent businesses on the same
schema and sharing the same vendor catalogue:

| business_id | Name | Type | Approx. daily revenue |
|---|---|---|---|
| `HSC001` | Harbour Street Cafe | Japanese — sushi/donburi/poke | NZD ~3.4k (primary scenario) |
| `NON002` | Nonna's Trattoria | Italian — casual dining | NZD ~2.2k (isolation control group) |

Two ingredients (`Chicken Breast`, `Panko Breadcrumb`) are purchased by
both businesses from the same vendors — this is intentional, to show that
the **vendor catalogue is shared** while **transaction data is isolated**
per business.

## Tables

### Per-business data (has `business_id`, subject to row-level isolation)
| File | Rows | Notes |
|---|---|---|
| `businesses.csv` | 2 | Business master (id, name, type, city) |
| `items.csv` | 43 | Menu + drinks combined (`item_type`: food/drink), surrogate `item_id` |
| `menu_ingredient_tags.csv` | 96 | Which ingredients appear in which item — **tag only, no precise gram quantities** (see design note below) |
| `purchase_ledger_all.csv` | 208 | 4 weeks of purchase transactions, both businesses |
| `daily_sales_all.csv` | 1,204 | 28 days × all items, both businesses, discount fields included |

### Shared reference data (no `business_id`, visible to all tenants)
| File | Rows | Notes |
|---|---|---|
| `ingredients.csv` | 50 | One row per ingredient, `ingredient_id` primary key |
| `vendor_offerings.csv` | 55 | Vendor × ingredient combinations — same ingredient can appear from multiple vendors (e.g. Fresh Salmon Fillet has 3 vendor offerings), enabling price-comparison queries |

### Mock invoices (for OCR / vision-extraction demo)
- `invoices/` — 28 purchase invoices for Harbour Street Cafe
- `invoices_non002/` — 16 purchase invoices for Nonna's Trattoria

## Design note: why there's no gram-level recipe table

An earlier version of this dataset used a precise bill-of-materials
(grams per ingredient per dish). This was deliberately replaced with
simple item↔ingredient tagging, because real kitchens rarely measure
ingredients precisely enough to make gram-level consumption tracking
realistic — and because requiring a restaurant owner to input exact
quantities for every dish creates unacceptable onboarding friction.
Instead, purchase-vs-sales correlation is computed by comparing purchase
volume of an ingredient against the aggregate sales of every item tagged
with that ingredient, over the same time window. This trades precision
for something that's both realistic to collect and still directionally
useful (e.g. "purchases are up but sales of related items are flat").

## Simulation parameters (HSC001)

- 5% ingredient loss during prep (trim/unusable)
- 12% final waste/spoilage rate
- 12% of sales are discounted (10–30% discount range, ~20% average)
- Drinks: negligible discount/waste
- NON002 uses slightly different parameters (10% waste, 10% discount
  share) as a deliberate contrast group

## Row-level isolation

Because this trial account is on Snowflake Standard Edition, native Row
Access Policies aren't available. Isolation is instead implemented via
secure views filtered on `CURRENT_ROLE()`, using a `BUSINESS_ROLE_MAP`
table (`HSC_OWNER_ROLE` → `HSC001`, `NON_OWNER_ROLE` → `NON002`). Full
detail and verification: [`../docs/coco_session_log.md`](../docs/coco_session_log.md).

## Example queries this dataset supports

- *"Compare the trend of salmon purchase volume against the trend of
  salmon-related menu item sales"* → uses `menu_ingredient_tags` +
  `purchase_ledger` + `daily_sales`, joined through `ingredients`
- *"Which vendor sells Fresh Salmon Fillet at the lowest price?"* → uses
  `vendor_offerings` + `ingredients`
- *"Which business had higher revenue this month?"* → answer depends on
  which Role is asking, since each Role only sees its own business_id
