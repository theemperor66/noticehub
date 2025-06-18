import smtplib
from email.message import EmailMessage

from src.utils.logger import logger
from src.config import settings


def send_email_notification(to_address: str, subject: str, body: str) -> bool:
    if not (settings.email_server and settings.email_username and settings.email_password):
        logger.warning("SMTP credentials missing; email not sent")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_username
    msg["To"] = to_address
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.email_server, settings.email_port) as server:
            server.starttls()
            server.login(settings.email_username, settings.email_password)
            server.send_message(msg)
        logger.info(f"Sent notification to {to_address}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification to {to_address}: {e}")
        return False
