# Harbour Street Cafe AI Copilot — Streamlit Demo

## How to Run

```bash
pip install -r requirements.txt --break-system-packages
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Open secrets.toml and fill in your actual Snowflake account info, Anthropic API key,
# and SMTP credentials (defaults to a free Mailtrap sandbox inbox — see below)
streamlit run app.py
```

## Screens

1. **Purchase Receipts** — Upload a receipt photo → Vision API auto-extracts
   items/vendor/price → review/edit in a table → saved to `RAW.PURCHASE_LEDGER`
2. **Sales Report** — Upload a daily cash-up report photo → auto-extracts
   sales quantity/revenue per item
3. **Ask AI** — Click an example question or type your own → the Cortex Agent
   answers, and the executed SQL can be expanded to view
4. **Dashboard** — Summary of this month's revenue/discount losses/purchase
   spend, salmon purchase-vs-sales trend, revenue ranking by item

## Supplier Price-Alert Emails (SMTP)

When a price increase is detected on invoice upload, the "📧 Notify supplier"
button sends an email via the SMTP provider configured under `[smtp]` in
`secrets.toml`. By default this points at [Mailtrap](https://mailtrap.io)'s
free sandbox inbox, so no real supplier ever receives an email during a demo
— everything lands in your Mailtrap inbox instead.

To switch providers (e.g. Gmail, Office365, Amazon SES) later, change
`provider` (and credentials) in `secrets.toml` — see
`streamlit_app/lib/smtp/providers.py` for the preset list. No application
code needs to change; `provider = "custom"` plus explicit `host`/`port` also
works for anything not in the preset list.

## Works Without a Snowflake Connection (Demo Mode)

If you don't enter Snowflake account info in the sidebar, each feature runs
on **sample data**. Useful when you just want to check the UI flow first.

## Things to Check Before Connecting for Real

1. **The REST API endpoint/auth method in `ask_cortex_agent()`** may need
   adjustment depending on your Snowflake account settings (PAT, OAuth,
   key-pair, etc). Official docs:
   https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
2. `current_role` (HSC_OWNER_ROLE / NON_OWNER_ROLE) must be granted to the
   actual Snowflake user account you're using.
3. When saving via `insert_rows()`, the sales report side still needs an
   `item_name → item_id` mapping added (currently the save button just shows
   a notice message — marked as TODO).

## Tips for a Live Demo

- Clicking through the example questions in order — "inventory → sales
  insights → tax prep" — makes for a natural storytelling flow.
- For receipt uploads, use real printed-and-photographed images prepared in
  advance (far more convincing than a screen capture of a mock invoice).
- If the dashboard tab shows "Connect to Snowflake to see this update with
  real data," that means you're not connected — be sure to test the
  connection before presenting.
