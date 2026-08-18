"""
Email content templates for automated supplier notifications.
"""


def price_alert_email(business_name: str, alert: dict) -> tuple[str, str, str]:
    """
    Build (subject, text_body, html_body) asking a supplier about a price increase.

    alert dict keys (see lib.alerts.detect_price_changes): ingredient, old_price,
    new_price, change_pct, unit, vendor, alternative_vendor, alternative_price,
    est_monthly_impact.
    """
    ingredient = alert.get("ingredient", "this item")
    old_price = alert.get("old_price", 0)
    new_price = alert.get("new_price", 0)
    pct = alert.get("change_pct", 0) * 100
    unit = alert.get("unit", "")
    vendor = alert.get("vendor", "")
    impact = alert.get("est_monthly_impact", 0)

    subject = f"Price increase on {ingredient} — {pct:.1f}% ({business_name})"

    text_body = (
        f"Hi {vendor} team,\n\n"
        f"We noticed the price of {ingredient} increased from "
        f"${old_price:.2f} to ${new_price:.2f} per {unit} ({pct:.1f}%), "
        f"an estimated ${impact:.2f}/month impact for us.\n\n"
        f"Could we discuss this increase, or revisit pricing for our next order?\n\n"
        f"Thanks,\n{business_name}"
    )

    alt_note = ""
    if alert.get("alternative_vendor"):
        alt_note = (
            f'<p style="color:#888">(For context, we\'re also comparing pricing with '
            f'{alert["alternative_vendor"]} at ${alert["alternative_price"]:.2f}/{unit}.)</p>'
        )

    html_body = (
        f"<p>Hi {vendor} team,</p>"
        f"<p>We noticed the price of <b>{ingredient}</b> increased from "
        f"<b>${old_price:.2f}</b> to <b>${new_price:.2f}</b> per {unit} "
        f"(<b>{pct:.1f}%</b>), an estimated <b>${impact:.2f}/month</b> impact for us.</p>"
        f"<p>Could we discuss this increase, or revisit pricing for our next order?</p>"
        f"{alt_note}"
        f"<p>Thanks,<br>{business_name}</p>"
    )

    return subject, text_body, html_body
