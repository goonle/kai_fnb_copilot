"""
Preset connection settings for common SMTP providers.

To switch providers later (Mailtrap -> Gmail -> Office365 -> SES -> ...),
change `provider` (and credentials) in secrets.toml — nothing in client.py
or templates.py needs to change. To support a brand new provider, just add
a preset here.
"""

PROVIDER_PRESETS = {
    "mailtrap": {"host": "sandbox.smtp.mailtrap.io", "port": 587, "use_tls": True},
    "gmail": {"host": "smtp.gmail.com", "port": 587, "use_tls": True},
    "office365": {"host": "smtp.office365.com", "port": 587, "use_tls": True},
    "ses": {"host": "email-smtp.us-east-1.amazonaws.com", "port": 587, "use_tls": True},
}


def resolve_smtp_config(cfg: dict) -> dict:
    """
    Merge a provider preset with explicit overrides from secrets.toml.

    cfg keys (all from the [smtp] table in secrets.toml):
      provider   -- one of PROVIDER_PRESETS, or "custom"
      host, port, use_tls -- optional explicit overrides (required if provider is "custom")
      user, password -- SMTP auth credentials
      from_addr  -- optional "From" address, defaults to `user`
    """
    provider = str(cfg.get("provider", "")).lower()
    preset = PROVIDER_PRESETS.get(provider, {})

    return {
        "provider": provider,
        "host": cfg.get("host") or preset.get("host"),
        "port": int(cfg.get("port") or preset.get("port", 587)),
        "use_tls": bool(cfg.get("use_tls", preset.get("use_tls", True))),
        "user": cfg.get("user", ""),
        "password": cfg.get("password", ""),
        "from_addr": cfg.get("from_addr") or cfg.get("user", ""),
    }
