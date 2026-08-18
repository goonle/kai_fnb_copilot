from .client import send_email, get_smtp_config
from .templates import price_alert_email

__all__ = ["send_email", "get_smtp_config", "price_alert_email"]
