import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL
from src.database import PropertyRecord
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """Send property notifications via email."""

    name = "email"

    def is_configured(self) -> bool:
        return all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL])

    async def notify(self, records: list[PropertyRecord]) -> bool:
        if not self.is_configured():
            logger.warning(f"[{self.name}] Not configured, skipping")
            return False

        if not records:
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Property Alert: {self.format_summary(records)}"
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFY_EMAIL

            # Plain text
            text_body = self._format_text(records)
            msg.attach(MIMEText(text_body, "plain"))

            # HTML
            html_body = self._format_html(records)
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())

            logger.info(f"[{self.name}] Email sent with {len(records)} properties")
            return True

        except Exception as e:
            logger.error(f"[{self.name}] Email failed: {e}")
            return False

    def _format_text(self, records: list[PropertyRecord]) -> str:
        lines = [
            f"Found {len(records)} new properties:",
            "",
            "=" * 50,
        ]

        for record in records:
            lines.append("")
            lines.append(self.format_record(record))
            lines.append("-" * 50)

        return "\n".join(lines)

    def _format_html(self, records: list[PropertyRecord]) -> str:
        html = [
            "<html><body>",
            f"<h2>Found {len(records)} new properties</h2>",
        ]

        for record in records:
            color = "#28a745" if record.record_type == "sale" else "#fd7e14"
            html.append(f"""
            <div style='margin: 20px 0; padding: 15px; border-left: 4px solid {color}; background: #f8f9fa;'>
                <h3 style='margin: 0 0 10px 0;'>🏠 {record.address}</h3>
                <p><strong>Price:</strong> {record.formatted_price}</p>
                <p><strong>Location:</strong> {record.city}, {record.state} {record.zip_code}</p>
                <p><strong>Type:</strong> {record.record_type.title()}</p>
                {"<p><strong>Date:</strong> " + record.sale_date + "</p>" if record.sale_date else ""}
                <p><strong>Source:</strong> {record.county.replace("_", " ").title()}</p>
                <p><a href='{record.url}' style='color: #007bff;'>View Property</a></p>
            </div>
            """)

        html.append("</body></html>")
        return "\n".join(html)
