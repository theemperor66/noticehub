from bs4 import BeautifulSoup
from src.utils.logger import logger


def parse_html_to_text(html_content: str) -> str:
    """Extracts plain text from HTML content."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        # Get text, ensuring good separation and stripping whitespace
        text = soup.get_text(separator="\n", strip=True)
        return text
    except Exception as e:
        logger.error(f"Error parsing HTML: {e}")
        return ""  # Return empty string or the original content if preferred


def clean_email_body(body: str) -> str:
    """Basic cleaning of email body.
    Can be expanded to remove signatures, disclaimers, etc.
    """
    # Example: remove common signature patterns (very basic)
    # lines = body.splitlines()
    # cleaned_lines = []
    # signature_keywords = ["-- ", "Best regards", "Sincerely"]
    # for line in lines:
    #     if any(keyword.lower() in line.lower() for keyword in signature_keywords):
    #         break # Stop at first sign of a common signature
    #     cleaned_lines.append(line)
    # return "\n".join(cleaned_lines)
    # For now, just return the body as is or with minimal whitespace cleanup
    return body.strip()


# WP2: Develop Pre-filters
def pre_filter_email(
    email_data: dict,
    sender_whitelist: list = None,
    sender_blacklist: list = None,
    subject_keywords: list = None,
) -> bool:
    """Determines if an email is relevant based on sender and subject keywords."""
    subject = email_data.get("subject", "").lower()
    sender = email_data.get("from", "").lower()

    # Filter by sender domains (whitelist)
    if sender_whitelist:
        if not any(domain in sender for domain in sender_whitelist):
            logger.debug(f"Email from '{sender}' not in whitelist. Skipping.")
            return False

    # Filter by sender domains (blacklist)
    if sender_blacklist:
        if any(domain in sender for domain in sender_blacklist):
            logger.debug(f"Email from '{sender}' is in blacklist. Skipping.")
            return False

    # Filter by keywords in the subject
    if subject_keywords:
        if not any(keyword.lower() in subject for keyword in subject_keywords):
            logger.debug(
                f"Email subject '{subject}' does not contain keywords. Skipping."
            )
            return False

    logger.info(
        f"Email (Subject: '{email_data.get('subject')}', From: '{email_data.get('from')}') passed pre-filters."
    )
    return True


if __name__ == "__main__":
    sample_html = """
    <html>
        <head><title>Test Email</title></head>
        <body>
            <p>Hello World!</p>
            <p>This is a <b>test message</b>.</p>
            <p>Regards,<br>Test Sender</p>
            <div style='display:none'>Hidden Content</div>
        </body>
    </html>
    """
    text_content = parse_html_to_text(sample_html)
    logger.info("Parsed HTML to Text:")
    logger.info(text_content)

    sample_email_relevant = {
        "subject": "Important Maintenance Notification for Service X",
        "from": "alerts@cloudprovider.com",
        "body_text": "Details about maintenance...",
    }
    sample_email_irrelevant_sender = {
        "subject": "Maintenance Update",
        "from": "newsletter@example.com",
        "body_text": "...",
    }
    sample_email_irrelevant_subject = {
        "subject": "Your Monthly Invoice",
        "from": "billing@cloudprovider.com",
        "body_text": "...",
    }

    keywords = ["Maintenance", "Outage", "Störung", "Wartung", "Incident"]
    whitelist = ["cloudprovider.com", "support.example.com"]
    blacklist = ["marketing@example.com", "spam@example.net"]

    logger.info(
        f"Testing relevant email: {pre_filter_email(sample_email_relevant, sender_whitelist=whitelist, subject_keywords=keywords)}"
    )
    logger.info(
        f"Testing irrelevant sender: {pre_filter_email(sample_email_irrelevant_sender, sender_whitelist=whitelist, subject_keywords=keywords)}"
    )
    logger.info(
        f"Testing blacklisted sender: {pre_filter_email({'subject': 'Maintenance', 'from': 'spam@example.net'}, sender_blacklist=blacklist, subject_keywords=keywords)}"
    )
    logger.info(
        f"Testing irrelevant subject: {pre_filter_email(sample_email_irrelevant_subject, sender_whitelist=whitelist, subject_keywords=keywords)}"
    )
