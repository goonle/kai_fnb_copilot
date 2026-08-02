import streamlit as st

st.set_page_config(page_title="Harbour Street Cafe AI Copilot", page_icon="🍣", layout="wide")

# ---------------------------------------------------------------------
# Secret setting
# ---------------------------------------------------------------------

sf_account = st.secrets.get("snowflake", {}).get("account", "")
sf_user = st.secrets.get("snowflake", {}).get("user", "")
sf_warehouse = st.secrets.get("snowflake", {}).get("warehouse", "COMPUTE_WH")
sf_database = st.secrets.get("snowflake", {}).get("database", "HARBOUR_CAFE")
sf_private_key = st.secrets.get("snowflake", {}).get("private_key", "")

# ---------------------------------------------------------------------------
# Snowflake connection helper
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_snowflake_connection_by_role(role):
    """
    Connects using key-pair authentication (RSA private key) instead of
    password + MFA. This avoids MFA prompts and password-lockout issues
    entirely, and is Snowflake's recommended method for programmatic access.

    Reads the unencrypted PKCS8 private key PEM text from st.secrets
    (snowflake.private_key) rather than a file on disk, since a raw .p8
    file isn't practical to ship with a deployment.
    """

    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    p_key = serialization.load_pem_private_key(sf_private_key.encode(), password=None)
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(
        account=sf_account, user=sf_user, private_key=pkb,
        warehouse=sf_warehouse, database=sf_database, role=role,
    )

def get_cortex_agent_url():
    agent_schema = st.secrets.get("snowflake", {}).get("agent_schema", "ANALYTIC")
    agent_name = "FOOD_INTEL_AGENT"
    url = (f"https://{sf_account}.snowflakecomputing.com/api/v2/databases/"
            f"{sf_database}/schemas/{agent_schema}/agents/{agent_name}:run")
    return url