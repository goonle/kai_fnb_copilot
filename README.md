# Harbour Street Cafe — F&B AI Copilot

**Snowflake CoCo CLI Hackathon 2026 submission**
Problem statement: *Domain-Specific AI Copilot* (F&B / hospitality)

An AI copilot for small food & beverage businesses that turns purchase
invoices and daily sales (cash-up) records into a natural-language
analytics layer — built on Snowflake, with the semantic layer and Cortex
Agent generated through conversational prompts to **Snowflake CoCo CLI**.

> ⚠️ All business names, vendor names, and transaction data in this repo
> are **synthetic**. See [`data/README.md`](data/README.md) for details.

---

## 🎥 Demo

- Demo video: `<link to be added>`
- Live app (if deployed): `<link to be added>`

---

## What it does

- **Ingests purchase invoices and daily sales reports** from photos, using
  an LLM vision model to extract structured line items
- **Answers natural-language questions** about the business, e.g.:
  - *"Compare the trend of salmon purchase volume against the trend of
    salmon-related menu item sales"*
  - *"Which vendor sells Fresh Salmon Fillet at the lowest price?"*
  - *"Which items were sold at a discount this week, and what was the
    total discount loss?"*
- **Multi-tenant from day one** — two independent businesses
  (Harbour Street Cafe / Nonna's Trattoria) share the same schema and
  vendor catalog, but each Role can only see its own transaction data
- **Governance-aware** — row-level isolation enforced at the SQL layer,
  not by prompting the AI to "be careful"

---

## Why this problem

Existing accounting tools (e.g. Xero) record *what was spent*, but not
*whether it was a good decision* — there's no cross-vendor price
comparison, and no way to ask a plain-language question about how
purchasing and sales relate to each other. This project fills that gap
without asking the business owner to do anything more complex than
uploading a photo and typing a question.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  Streamlit App   │────▶│  Snowflake        │────▶│  Cortex Agent       │
│  (upload, chat,  │     │  RAW + ANALYTIC   │     │  (FOOD_INTEL_AGENT) │
│   dashboard)     │◀────│  schemas          │◀────│  + Semantic View    │
└─────────────────┘     └──────────────────┘     └────────────────────┘
        │                        │
        ▼                        ▼
 Vision API extracts      Secure views enforce
 structured data from     per-business row-level
 receipt/report photos    isolation (Role-based)
```

- **Data model**: 7 core tables (`businesses`, `ingredients`,
  `vendor_offerings`, `items`, `menu_ingredient_tags`, `purchase_ledger`,
  `daily_sales`) — see [`schema.sql`](schema.sql)
- **Semantic layer**: built via CoCo CLI prompts on top of 4 joined
  `ANALYTIC` views, with `INGREDIENTS` as the central hub connecting
  purchase, sales, and vendor-pricing data
- **Governance**: this trial account is on Standard Edition, which
  doesn't support native Row Access Policies, so row-level isolation is
  implemented via secure views filtered on `CURRENT_ROLE()` — see
  [`docs/coco_session_log.md`](docs/coco_session_log.md) for the full
  reasoning and verification

---

## Built with CoCo CLI

The semantic view, Cortex Agent, and all schema/view objects in this
project were created through natural-language prompts to Snowflake
CoCo CLI, not hand-written SQL. The full session — including two real
bugs CoCo found and fixed (unbounded date filters, and a Row Access
Policy → secure view fallback when the feature wasn't available on this
account edition) — is documented in:

- [`docs/coco_prompts_en.md`](docs/coco_prompts_en.md) — the exact
  prompts used, in order
- [`docs/coco_session_log.md`](docs/coco_session_log.md) — the narrated,
  verified transcript of the actual session, with every returned number
  cross-checked against the source CSVs

---

## Repo structure

```
.
├── README.md                    (this file)
├── schema.sql                   Snowflake DDL for all 7 core tables
├── data/
│   ├── businesses.csv, items.csv, ingredients.csv,
│   │   vendor_offerings.csv, menu_ingredient_tags.csv,
│   │   purchase_ledger_all.csv, daily_sales_all.csv
│   ├── invoices/                28 mock purchase invoices (Harbour St Cafe)
│   ├── invoices_non002/         16 mock purchase invoices (Nonna's Trattoria)
│   └── README.md                dataset design notes & disclaimers
├── docs/
│   ├── coco_prompts_en.md       prompts sent to CoCo CLI, in order
│   └── coco_session_log.md      narrated + verified session transcript
└── streamlit_app/
    ├── app.py                   4-tab demo app (upload, chat, dashboard)
    ├── requirements.txt
    ├── README.md                setup & run instructions
    └── .streamlit/secrets.toml.example
```

---

## Running the demo app

```bash
cd streamlit_app
pip install -r requirements.txt --break-system-packages
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in your Snowflake account + Anthropic API key in secrets.toml
streamlit run app.py
```

Without Snowflake credentials configured, the app runs in **demo mode**
with sample data, so the UI flow can be reviewed without a live account.
See [`streamlit_app/README.md`](streamlit_app/README.md) for details.

---

## Roadmap (out of scope for this submission)

- Staff scheduling / rostering assist
- AI-suggested recipe tagging for new menu items (no manual gram-level
  input required)
- Anonymized cross-business benchmarking once enough tenants are onboarded
- Native Row Access Policy once on Enterprise Edition

---

## Disclaimer

This is a hackathon prototype using entirely synthetic data. No real
business, vendor, or financial data is included. See
[`data/README.md`](data/README.md) for the full disclaimer on vendor
names used in the mock invoices.
