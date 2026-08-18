"""
Harbour Street Cafe - AI Copilot Demo
======================================
4-tab layout:
  1. Purchase invoice upload + preview
  2. Daily sales (cash-up) report upload + preview
  3. Cortex Agent chat (with suggested question buttons)
  4. Dashboard (purchase/sales correlation, discount loss summary)

Run: streamlit run app.py
Requires: .streamlit/secrets.toml (see secrets.toml.example)
"""
import streamlit as st
import pandas as pd
import altair as alt
import json
import base64
from datetime import date
import pathlib
import os
import fitz
from lib.snowflake.conn import get_snowflake_connection_by_role, get_cortex_agent_url, sf_account, sf_user
from lib.invoice import save_purchase_invoice
from lib.sales import save_daily_sales
from lib.alerts import detect_price_changes
from lib.actions import record_alert, update_menu_price, suggest_price_adjustment, update_waste_pct
from lib.smtp import send_email, price_alert_email



def run_sql(query, params=None):
    """Run SQL under the currently selected role. Falls back to demo mode if no connection info."""
    try:
        conn = get_snowflake_connection_by_role(current_role)
        cur = conn.cursor()
        cur.execute(query, params or {})
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        st.error(f"Snowflake query failed: {e}")
        return None


def insert_rows(table, rows: list[dict]):
    """INSERT a list of dicts into the given table."""
    if not rows:
        return False

    try:
        conn = get_snowflake_connection_by_role(current_role)
        cur = conn.cursor()
        cols = list(rows[0].keys())
        placeholders = ", ".join([f"%({c})s" for c in cols])
        col_str = ", ".join(cols)
        query = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
        cur.executemany(query, rows)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Save failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Cortex Agent call helper (REST API)
# ---------------------------------------------------------------------------
QUOTA_SHORTAGE_MESSAGE = (
    "⏳ **AI token/credit limit reached.** The Cortex Agent has hit its usage "
    "limit for now (rate limit, trial credits, or budget exhausted) — this "
    "isn't a bug, just a temporary quota. Please try again later."
)


def _is_quota_shortage(status_code: int, text: str) -> bool:
    """Heuristic: does this failure look like a rate-limit/credit/budget shortage
    rather than a genuine bug? HTTP 429 always counts; otherwise look for
    common quota-related keywords in the error text."""
    if status_code in (429, 402):
        return True
    lowered = (text or "").lower()
    keywords = (
        "rate limit", "rate-limit", "too many requests", "quota", "budget",
        "credit", "exceeded", "throttle", "insufficient funds",
    )
    return any(kw in lowered for kw in keywords)


def ask_cortex_agent(question: str):
    """
    Calls the Cortex Agent REST API.
    The exact endpoint/auth method may need adjusting depending on your
    Snowflake account setup.
    Docs: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
    """
    try:
        import requests
        # Prefer a Programmatic Access Token (PAT) if one is configured — this
        # is what Snowflake's docs recommend for the Cortex REST APIs. Falling
        # back to the connector's session token often returns an empty/HTML
        # response instead of JSON, which is why this is checked first.
        pat_token = st.secrets.get("snowflake", {}).get("pat_token", "")
        if pat_token:
            token = pat_token
            auth_header = f"Bearer {token}"
        else:
            conn = get_snowflake_connection_by_role(current_role)
            token = conn.rest.token
            auth_header = f'Snowflake Token="{token}"'

        url = get_cortex_agent_url()
        
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }
        body = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
        }
        resp = requests.post(url, headers=headers, json=body, timeout=30)

        # Show raw response details before attempting to parse, so failures
        # are diagnosable instead of just "Expecting value: line 1 column 1"
        if resp.status_code != 200:
            if _is_quota_shortage(resp.status_code, resp.text):
                return {"answer": QUOTA_SHORTAGE_MESSAGE, "sql": None, "chart_data": None,
                        "quota_exceeded": True}
            return {
                "answer": f"Agent call failed with HTTP {resp.status_code}.\n\n"
                          f"Response body (first 1000 chars):\n{resp.text[:1000]}",
                "sql": None, "chart_data": None,
            }
        if not resp.text.strip():
            return {
                "answer": "Agent call returned HTTP 200 but an empty body. "
                          "This usually means the auth token isn't valid for the REST API "
                          "(session tokens from the connector often don't work here — "
                          "try a Programmatic Access Token / PAT instead).",
                "sql": None, "chart_data": None,
            }

        # The Cortex Agents REST API returns Server-Sent Events (SSE), not a
        # single JSON blob — even on success. Format is lines like:
        #   event: <type>
        #   data: {...json...}
        # ending with "data: [DONE]". Parse every "data:" line as JSON and
        # pull out any text / SQL content we find, tolerating different
        # possible payload shapes since the exact schema isn't guaranteed.
        answer_text = ""
        sql_used = None
        error_message = None

        for line in resp.text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]" or not payload:
                continue
            try:
                event = json.loads(payload)
            except Exception:
                continue

            if isinstance(event, dict) and "message" in event and "code" in event:
                # This matches the shape of the error we saw:
                # {"message": "...", "code": "...", "request_id": "..."}
                error_message = event.get("message")
                continue

            # Try a few common shapes for text/SQL content
            content_blocks = []
            if isinstance(event, dict):
                if "content" in event:
                    content_blocks = event["content"]
                elif "delta" in event and isinstance(event["delta"], dict):
                    content_blocks = event["delta"].get("content", [])

            for item in content_blocks or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    answer_text += item.get("text", "")
                if item.get("type") == "tool_use":
                    tool_input = item.get("tool_use", {}).get("input", {})
                    if isinstance(tool_input, dict) and tool_input.get("query"):
                        sql_used = tool_input["query"]

        if error_message:
            if _is_quota_shortage(resp.status_code, error_message):
                return {"answer": QUOTA_SHORTAGE_MESSAGE, "sql": None, "chart_data": None,
                        "quota_exceeded": True}
            return {
                "answer": f"Agent returned an error: {error_message}",
                "sql": None, "chart_data": None,
            }

        return {"answer": answer_text or f"Received a response but couldn't extract any text from it.\n\n"
                                          f"Raw response (first 1000 chars):\n{resp.text[:1000]}",
                "sql": sql_used, "chart_data": None}
    except Exception as e:
        if _is_quota_shortage(0, str(e)):
            return {"answer": QUOTA_SHORTAGE_MESSAGE, "sql": None, "chart_data": None,
                    "quota_exceeded": True}
        return {"answer": f"Agent call failed: {e}\n\n(You may need to adjust the REST API endpoint/auth "
                          f"settings to match your account environment.)",
                "sql": None, "chart_data": None}


# ---------------------------------------------------------------------------
# Extract structured data from receipt/report images via Vision API
# ---------------------------------------------------------------------------
def extract_structured_data(image_bytes: bytes, file_name:str, doc_type: str) -> dict:
    """
    Extracts structured data from a receipt/report image using Snowflake's
    native AI_COMPLETE multimodal function — no external Anthropic API key
    needed. The image is staged temporarily, analyzed via SQL, then removed.
 
    doc_type: 'purchase_invoice' or 'sales_report'
    """
    if not sf_account or not sf_user:
        st.warning("⚠️ Not connected to Snowflake, returning sample demo data.")
        return {}  # (keep your existing demo-mode fallback here)
 
    conn = get_snowflake_connection_by_role(current_role)
    cur = conn.cursor()
    stage_name = "RAW.RECEIPT_IMAGES"
 
    try:
        # # 1. Make sure the stage exists (id empotent, safe to run every time)
        # cur.execute(f"""
        #     CREATE STAGE IF NOT EXISTS {stage_name}
        #     DIRECTORY = (ENABLE = true)
        #     ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
        # """)
 
        # 2. Upload the image bytes to the stage.
        # PUT requires a local file path, so write to a temp file first.
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=f"_{file_name}", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
 
        cur.execute(f"PUT file://{tmp_path} @{stage_name} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        staged_filename = os.path.basename(tmp_path)
        os.remove(tmp_path)
 
        # 3. Build the extraction prompt
        if doc_type == "purchase_invoice":
            prompt = (
                "This is a purchase invoice from a food & beverage vendor. Formats vary by vendor "
                "(e.g. pack size may appear in the description like 'Chicken Breast (1kg/pack)', "
                "or as a separate column, or be absent). Normalize as follows:\n"
                "- 'ingredient': the item name WITHOUT the pack size/unit annotation.\n"
                "- 'qty_packs': the quantity of packs/units ordered (not total weight).\n"
                "- 'pack_size': the numeric size per pack, extracted from the description if needed "
                "(e.g. '1kg/pack' -> pack_size=1, unit='kg'). If genuinely absent, use 1.\n"
                "- 'unit': the unit of measure (kg, L, ea, pkt, etc). If absent, use 'ea'.\n"
                "- 'unit_price': price per pack, not per line total.\n"
                "- 'category': best-fit ingredient category, chosen from this exact list: "
                "'Fresh Seafood', 'Fresh Meat', 'Fresh Produce', 'Frozen Protein', 'Frozen Goods', "
                "'Asian Specialty Imports', 'Italian Specialty Imports', 'Dry Goods & Pantry', 'Other'.\n"
                "Respond with ONLY valid JSON in this exact shape, no other text, no markdown fences:\n"
                '{"vendor": "...", "issue_date": "YYYY-MM-DD", "items": '
                '[{"ingredient": "...", "qty_packs": 0, "pack_size": 0, "unit": "...", '
                '"unit_price": 0.0, "category": "..."}]}'
            )
        else:
            prompt = (
                "This is a daily sales / cash-up report from a restaurant. "
                "Extract the sale date and each menu item sold with its quantity and revenue. "
                "Respond with ONLY valid JSON in this exact shape, no other text: "
                '{"sale_date": "YYYY-MM-DD", "items": '
                '[{"item_name": "...", "qty_sold": 0, "revenue": 0.0}]}'
            )
 
        # 4. Call AI_COMPLETE with the staged image
        cur.execute(
            """
                SELECT AI_COMPLETE(
                    'claude-sonnet-4-6',
                    %(prompt)s,
                    TO_FILE(%(stage)s, %(filename)s)
                ) AS extracted
            
            """,
            {"stage": f"@{stage_name}", "filename": staged_filename, "prompt": prompt},
        )
        result_text = cur.fetchone()[0]
        cleaned = result_text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)

        if isinstance(parsed, str):
            parsed = json.loads(parsed)   # just in case double encoded

        # 5. Clean up the staged file
        cur.execute(f"REMOVE @{stage_name}/{staged_filename}")
        return parsed   # 반드시 dict를 리턴해야 함, 문자열 X
 
    except Exception as e:
        st.error(f"Image recognition via Snowflake AI_COMPLETE failed: {e}")
        return {}



# ---------------------------------------------------------------------------
# Sidebar: Snowflake connection + Role (business) switcher
# ---------------------------------------------------------------------------
st.sidebar.title("F&B AI Copilot")
st.sidebar.caption("AI Copilot for F&B purchasing & sales intelligence")

role_options = {
    "Harbour Street Cafe (HSC001)": "HSC_OWNER_ROLE",
    "Nonna's Trattoria (NON002)": "NON_OWNER_ROLE",
}
selected_business = st.sidebar.selectbox("Currently logged in as", list(role_options.keys()))
current_role = role_options[selected_business]
business_id = "HSC001" if "HSC" in current_role else "NON002"
st.sidebar.info(f"Current Role: `{current_role}`\n\nThis account can only see its own business's data.")

# Switching businesses mid-conversation would otherwise leak the previous
# business's chat history/context into the new one, so reset it here.
if st.session_state.get("chat_business_id") != business_id:
    st.session_state["chat_history"] = []
    st.session_state["chat_business_id"] = business_id





# ---------------------------------------------------------------------------
# Main screen: tabs
# ---------------------------------------------------------------------------
st.title("🍣 F&B AI Copilot")
st.caption(f"Current business: **{selected_business}**")

tab_purchase, tab_sales, tab_chat, tab_dashboard = st.tabs(
    ["📥 Purchase Invoices", "💰 Sales Report", "💬 Ask the AI", "📊 Dashboard"]
)

# --- Tab 1: Purchase invoice upload ---
with tab_purchase:
    st.subheader("Upload a purchase invoice")
    uploaded_invoice = st.file_uploader("Upload a photo of the invoice", type=["jpg", "jpeg", "png", "pdf"], key="invoice")
    if uploaded_invoice:
        col1, col2 = st.columns([1, 1])
        with col1:
            if uploaded_invoice.type == "application/pdf":
                doc = fitz.open(stream=uploaded_invoice.getvalue(), filetype="pdf")
                page = doc[0]
                pix = page.get_pixmap(dpi=100)
                st.image(pix.tobytes("png"), caption=f"{uploaded_invoice.name} (page 1)", use_container_width=True)
            else:
                st.image(uploaded_invoice, caption="Uploaded invoice", use_container_width=True)
        with col2:
            cache_key = f"invoice_extract_{uploaded_invoice.name}_{uploaded_invoice.size}"
            if cache_key not in st.session_state:
                with st.spinner("Extracting data from the invoice..."):
                    st.session_state[cache_key] = extract_structured_data(
                        uploaded_invoice.getvalue(), uploaded_invoice.name, "purchase_invoice"
                    )
            data = st.session_state[cache_key]

            if data and isinstance(data, dict):
                st.success(f"Vendor: **{data.get('vendor', '?')}** / Date: **{data.get('issue_date', '?')}**")
                df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="invoice upload")

                # --- Proactive Price Alert Panel ---
                if sf_account:  # only if connected to Snowflake
                    try:
                        alert_conn = get_snowflake_connection_by_role(current_role)
                        alert_cur = alert_conn.cursor()
                        alerts = detect_price_changes(
                            alert_cur, business_id, data.get("vendor", ""),
                            edited_df.to_dict("records")
                        )
                        if alerts:
                            st.divider()
                            st.warning(f"⚠️ **{len(alerts)} price increase(s) detected!**")
                            for idx, alert in enumerate(alerts):
                                pct_str = f"{alert['change_pct']*100:.1f}%"
                                with st.expander(
                                    f"🔺 {alert['ingredient']}: +{pct_str} "
                                    f"(${alert['old_price']:.2f} → ${alert['new_price']:.2f}/{alert['unit']})"
                                ):
                                    col_a, col_b = st.columns(2)
                                    with col_a:
                                        st.metric("Estimated monthly impact",
                                                  f"+${alert['est_monthly_impact']:.2f}")
                                    with col_b:
                                        if alert["alternative_vendor"]:
                                            st.info(
                                                f"💡 **{alert['alternative_vendor']}** offers this at "
                                                f"${alert['alternative_price']:.2f}/{alert['unit']}"
                                            )
                                        else:
                                            st.caption("No alternative vendor found")

                                    # Action buttons
                                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                                    with btn_col1:
                                        if st.button("📝 Record alert", key=f"record_alert_{idx}"):
                                            try:
                                                alert_id = record_alert(alert_cur, business_id, alert)
                                                alert_conn.commit()
                                                st.success(f"Alert {alert_id} recorded")
                                            except Exception as e:
                                                st.error(f"Failed: {e}")
                                    with btn_col2:
                                        if alert.get("ingredient_id"):
                                            suggestions = suggest_price_adjustment(
                                                alert_cur, business_id,
                                                alert["ingredient_id"], alert["change_pct"]
                                            )
                                            if suggestions and st.button(
                                                "💰 Update menu prices", key=f"update_price_{idx}"
                                            ):
                                                try:
                                                    for s in suggestions:
                                                        update_menu_price(alert_cur, s["item_id"], s["suggested_price"])
                                                    alert_conn.commit()
                                                    st.success(
                                                        f"Updated {len(suggestions)} menu item(s): "
                                                        + ", ".join(f"{s['item_name']} → ${s['suggested_price']:.2f}" for s in suggestions)
                                                    )
                                                except Exception as e:
                                                    st.error(f"Failed: {e}")
                                    with btn_col3:
                                        if alert.get("ingredient_id"):
                                            new_waste = st.number_input(
                                                "Waste %", min_value=0.0, max_value=50.0,
                                                value=5.0, step=1.0, key=f"waste_{idx}"
                                            )
                                            if st.button("Set waste %", key=f"set_waste_{idx}"):
                                                try:
                                                    update_waste_pct(alert_cur, alert["ingredient_id"], new_waste)
                                                    alert_conn.commit()
                                                    st.success(f"Waste % set to {new_waste}%")
                                                except Exception as e:
                                                    st.error(f"Failed: {e}")
                                    with btn_col4:
                                        supplier_email = st.text_input(
                                            "Supplier email", key=f"supplier_email_{idx}",
                                            placeholder="orders@supplier.com",
                                        )
                                        if st.button("📧 Notify supplier", key=f"notify_supplier_{idx}"):
                                            if not supplier_email:
                                                st.error("Enter a supplier email first")
                                            else:
                                                try:
                                                    business_name = selected_business.split(" (")[0]
                                                    subject, text_body, html_body = price_alert_email(business_name, alert)
                                                    send_email(supplier_email, subject, text_body, html_body)
                                                    st.success(f"Email sent to {supplier_email}")
                                                except Exception as e:
                                                    st.error(f"Failed to send email: {e}")
                            st.divider()
                    except Exception as e:
                        pass  # silently skip alerts if DB not available

                if st.button("✅ Save this data", key="save_invoice"):
                    try:
                        conn = get_snowflake_connection_by_role(current_role)
                        cur = conn.cursor()
                        summary = save_purchase_invoice(
                            cur,
                            business_id=business_id,
                            vendor=data.get("vendor", ""),
                            week_start=data.get("issue_date"),
                            items=edited_df.to_dict("records"),
                        )
                        conn.commit()
                        msg = f"{summary['rows_saved']} line item(s) saved under vendor **{summary['vendor']}**."
                        if summary["created_ingredients"]:
                            msg += f" New ingredients created: {', '.join(summary['created_ingredients'])}."
                        st.success(msg)
                    except Exception as e:
                        st.error(f"Save failed: {e}")
            elif data:
                st.error(f"Unexpected data format: {data}")
            else:
                st.error("Fail to extract text.")

# --- Tab 2: Daily sales (cash-up) report upload ---
with tab_sales:
    st.subheader("Upload a daily sales (cash-up) report")
    uploaded_report = st.file_uploader("Upload a photo of the report", type=["jpg", "jpeg", "png"], key="sales")
    if uploaded_report:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(uploaded_report, caption="Uploaded sales report", use_container_width=True)
        with col2:
            cache_key = f"sales_extract_{uploaded_report.name}_{uploaded_report.size}"
            if cache_key not in st.session_state:
                with st.spinner("Extracting data from the report..."):
                    st.session_state[cache_key] = extract_structured_data(
                        uploaded_report.getvalue(), uploaded_report.name, "sales_report"
                    )
            data = st.session_state[cache_key]

            if data:
                st.success(f"Sale date: **{data.get('sale_date', '?')}**")
                df = pd.DataFrame(data.get("items", []))
                edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="report upload")
                if st.button("✅ Save this data", key="save_sales"):
                    try:
                        conn = get_snowflake_connection_by_role(current_role)
                        cur = conn.cursor()
                        summary = save_daily_sales(
                            cur,
                            business_id=business_id,
                            sale_date=data.get("sale_date"),
                            items=edited_df.to_dict("records"),
                        )
                        conn.commit()
                        msg = f"{summary['rows_saved']} line item(s) saved."
                        if summary["skipped_items"]:
                            msg += (f" Skipped (no matching menu item in ITEMS): "
                                    f"{', '.join(summary['skipped_items'])}.")
                        st.success(msg)
                    except Exception as e:
                        st.error(f"Save failed: {e}")

# --- Tab 3: Chat ---
with tab_chat:
    st.subheader("Ask anything")

    suggested_questions = {
        "Supplier optimization": [
            "Which vendor sells Fresh Salmon Fillet at the lowest price?",
            "What are my biggest cost-saving opportunities if I switch to cheaper vendors?",
        ],
        "Menu margins & waste": [
            "Which menu items have gross margins below 50%?",
            "Show items where waste-adjusted COGS exceeds 40% of selling price",
        ],
        "Sales insights": [
            "What are the top 5 best-selling menu items this month?",
            "Which items were sold at a discount this week, and what was the total discount loss?",
        ],
        "Purchase trends": [
            "Compare the trend of salmon purchase volume against salmon-related menu sales",
            "Summarize this month's spending by ingredient category",
        ],
    }

    st.write("**Here are some things you can ask:**")
    for category, questions in suggested_questions.items():
        st.caption(category)
        cols = st.columns(len(questions))
        for col, q in zip(cols, questions):
            if col.button(q, key=f"suggest_{q}"):
                st.session_state["pending_question"] = q

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            if msg.get("quota_exceeded"):
                st.warning(msg["content"])
            else:
                st.write(msg["content"])
            if msg.get("sql"):
                with st.expander("View SQL executed"):
                    st.code(msg["sql"], language="sql")

    user_question = st.chat_input("Type your question...")
    pending = st.session_state.pop("pending_question", None)
    question_to_ask = pending or user_question

    if question_to_ask:
        st.session_state["chat_history"].append({"role": "user", "content": question_to_ask})
        with st.chat_message("user"):
            st.write(question_to_ask)
        with st.chat_message("assistant"):
            with st.spinner("Generating an answer..."):
                result = ask_cortex_agent(question_to_ask)
            if result.get("quota_exceeded"):
                st.warning(result["answer"])
            else:
                st.write(result["answer"])
            if result.get("sql"):
                with st.expander("View SQL executed"):
                    st.code(result["sql"], language="sql")
        st.session_state["chat_history"].append({
            "role": "assistant", "content": result["answer"], "sql": result.get("sql"),
            "quota_exceeded": result.get("quota_exceeded", False),
        })

# --- Tab 4: Dashboard ---
with tab_dashboard:
    st.subheader("This month's summary")

    col1, col2, col3 = st.columns(3)
    # Demo/mock data is anchored to fixed dates, so "this month" is scoped to the
    # most recent month actually present in each table rather than literal
    # CURRENT_DATE — otherwise the cards go blank once real time drifts past
    # the data's date range.
    sales_metrics_df = run_sql(
        f"""
        WITH ref AS (
            SELECT DATE_TRUNC('MONTH', MAX(sale_date)) AS month_start
            FROM ANALYTIC.SALES_DETAIL WHERE business_id = '{business_id}'
        )
        SELECT ref.month_start,
               SUM(revenue_number) AS total_revenue,
               SUM(unit_price_number * qty_sold_discounted * discount_rate) AS discount_loss
        FROM ANALYTIC.SALES_DETAIL, ref
        WHERE business_id = '{business_id}'
          AND sale_date >= ref.month_start
          AND sale_date <  DATEADD('MONTH', 1, ref.month_start)
        GROUP BY ref.month_start
        """
    )
    purchase_metrics_df = run_sql(
        f"""
        WITH ref AS (
            SELECT DATE_TRUNC('MONTH', MAX(week_start)) AS month_start
            FROM ANALYTIC.PURCHASE_DETAIL WHERE business_id = '{business_id}'
        )
        SELECT ref.month_start, SUM(line_total_number) AS total_spend
        FROM ANALYTIC.PURCHASE_DETAIL, ref
        WHERE business_id = '{business_id}'
          AND week_start >= ref.month_start
          AND week_start <  DATEADD('MONTH', 1, ref.month_start)
        GROUP BY ref.month_start
        """
    )

    has_sales = sales_metrics_df is not None and not sales_metrics_df.empty
    sales_month_label = pd.to_datetime(sales_metrics_df["MONTH_START"].iloc[0]).strftime("%b %Y") if has_sales else None
    has_purchases = purchase_metrics_df is not None and not purchase_metrics_df.empty
    purchase_month_label = pd.to_datetime(purchase_metrics_df["MONTH_START"].iloc[0]).strftime("%b %Y") if has_purchases else None

    with col1:
        val = sales_metrics_df["TOTAL_REVENUE"].iloc[0] if has_sales else 0
        st.metric(f"Revenue ({sales_month_label})" if sales_month_label else "Revenue this month",
                   f"NZD ${val:,.2f}" if val else "No data")
    with col2:
        val = sales_metrics_df["DISCOUNT_LOSS"].iloc[0] if has_sales else 0
        st.metric(f"Discount loss ({sales_month_label})" if sales_month_label else "Discount loss",
                   f"NZD ${val:,.2f}" if val else "No data")
    with col3:
        val = purchase_metrics_df["TOTAL_SPEND"].iloc[0] if has_purchases else 0
        st.metric(f"Purchases ({purchase_month_label})" if purchase_month_label else "Purchases this month",
                   f"NZD ${val:,.2f}" if val else "No data")

    st.divider()
    st.write("**Salmon purchase vs. sales trend** (last 12 weeks)")
    trend_df = run_sql(
        f"""
        WITH purchases AS (
            SELECT week_start, SUM(qty_packs * pack_size) AS purchased_kg
            FROM ANALYTIC.PURCHASE_DETAIL
            WHERE business_id = '{business_id}' AND LOWER(ingredient_name) LIKE '%salmon%'
            GROUP BY week_start
        ),
        sales AS (
            SELECT DATE_TRUNC('week', sale_date) AS week_start, SUM(total_qty_sold) AS sold_units
            FROM ANALYTIC.INGREDIENT_SALES_LINK
            WHERE business_id = '{business_id}' AND LOWER(ingredient_name) LIKE '%salmon%'
            GROUP BY DATE_TRUNC('week', sale_date)
        )
        SELECT COALESCE(p.week_start, s.week_start) AS week_start,
               COALESCE(p.purchased_kg, 0) AS purchased_kg,
               COALESCE(s.sold_units, 0) AS sold_units
        FROM purchases p
        FULL OUTER JOIN sales s ON p.week_start = s.week_start
        ORDER BY week_start DESC
        LIMIT 12
        """
    )
    if trend_df is not None and not trend_df.empty:
        trend_df = trend_df.sort_values("WEEK_START")
        trend_df["WEEK_LABEL"] = pd.to_datetime(trend_df["WEEK_START"]).dt.strftime("%b %d")
        trend_long = trend_df.melt(
            "WEEK_LABEL", value_vars=["PURCHASED_KG", "SOLD_UNITS"],
            var_name="series", value_name="value",
        )
        trend_chart = (
            alt.Chart(trend_long)
            .mark_line()
            .encode(
                x=alt.X("WEEK_LABEL:N", sort=list(trend_df["WEEK_LABEL"]), axis=alt.Axis(labelAngle=0), title=None),
                y=alt.Y("value:Q", title=None),
                color=alt.Color("series:N", title=None),
            )
        )
        st.altair_chart(trend_chart, use_container_width=True)
    else:
        st.info("No salmon purchase/sales data found for this business yet.")

    st.write("**Top 10 items by revenue**")
    top_items_df = run_sql(
        f"SELECT item_name, SUM(revenue_number) AS revenue FROM ANALYTIC.SALES_DETAIL "
        f"WHERE business_id = '{business_id}' GROUP BY item_name ORDER BY revenue DESC LIMIT 10"
    )
    if top_items_df is not None and not top_items_df.empty:
        bar_chart = (
            alt.Chart(top_items_df)
            .mark_bar()
            .encode(
                x=alt.X("ITEM_NAME:N", sort="-y", axis=alt.Axis(labelAngle=0), title=None),
                y=alt.Y("REVENUE:Q", title=None),
            )
        )
        st.altair_chart(bar_chart, use_container_width=True)
    else:
        st.info("Connect to Snowflake to see real data in this chart.")

    st.divider()
    st.write("**Recent Price Alerts**")
    alerts_df = run_sql(
        f"""
        SELECT ALERT_ID, INGREDIENT_NAME, VENDOR_NAME,
               OLD_PRICE_NUMBER, NEW_PRICE_NUMBER, CHANGE_PCT,
               ALTERNATIVE_VENDOR, ALTERNATIVE_PRICE,
               EST_MONTHLY_IMPACT, STATUS, CREATED_AT
        FROM RAW.PRICE_ALERTS
        WHERE BUSINESS_ID = '{business_id}'
        ORDER BY CREATED_AT DESC
        LIMIT 20
        """
    )
    if alerts_df is not None and not alerts_df.empty:
        # Color-code status
        def style_status(val):
            colors = {"pending": "orange", "acknowledged": "blue", "acted": "green"}
            return f"color: {colors.get(val, 'black')}"

        st.dataframe(
            alerts_df.style.applymap(style_status, subset=["STATUS"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No price alerts recorded yet. Upload an invoice to trigger price-change detection.")
