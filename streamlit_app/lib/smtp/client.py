"""
Provider-agnostic SMTP sender.

Reads connection settings from st.secrets["smtp"] via providers.resolve_smtp_config().
Swapping SMTP providers is a secrets.toml change only — this module is unaware
of Mailtrap/Gmail/etc specifics.
"""

import smtplib
from email.message import EmailMessage

import streamlit as st

from .providers import resolve_smtp_config


def get_smtp_config() -> dict:
    return resolve_smtp_config(dict(st.secrets.get("smtp", {})))


def send_email(to_addr: str, subject: str, text_body: str, html_body: str = None) -> None:
    """
    Send an email through the SMTP provider configured in secrets.toml.
    Raises RuntimeError/OSError on misconfiguration or send failure — callers
    should catch and surface the error in the UI.
    """
    cfg = get_smtp_config()
    if not cfg["host"] or not cfg["user"]:
        raise RuntimeError("SMTP is not configured — set [smtp] in .streamlit/secrets.toml")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
        if cfg["use_tls"]:
            server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)
