from typing import List, Optional, Tuple
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
from datetime import datetime
from bs4 import BeautifulSoup
from src.utils.logger import logger # Corrected import path
from src.config import settings # Import settings

class EmailClient:
    def __init__(self, server: str, port: int, username: str, password: str, folder: str = "INBOX"):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder
        self.connection: Optional[imaplib.IMAP4_SSL] = None

    def _is_email_relevant(self, subject_str: str, from_str: str) -> bool:
        """Check if an email is relevant based on sender and subject filters."""
        # Parse sender's email address and extract domain
        parsed_from = parseaddr(from_str)
        sender_email = parsed_from[1].lower() # email_address part, lowercased
        sender_domain = sender_email.split('@')[-1] if '@' in sender_email else ""

        subject_str_lower = subject_str.lower()

        # Sender Domain Whitelist Check
        if settings.email_sender_domain_whitelist:
            if not sender_domain or sender_domain not in settings.email_sender_domain_whitelist:
                logger.debug(f"Email from '{sender_email}' (domain: '{sender_domain}') filtered out: sender domain not in whitelist.")
                return False
        
        # Sender Domain Blacklist Check
        if settings.email_sender_domain_blacklist:
            if sender_domain and sender_domain in settings.email_sender_domain_blacklist:
                logger.debug(f"Email from '{sender_email}' (domain: '{sender_domain}') filtered out: sender domain in blacklist.")
                return False

        # Subject Keywords Whitelist Check
        if settings.email_subject_keywords_whitelist:
            if not any(keyword in subject_str_lower for keyword in settings.email_subject_keywords_whitelist):
                logger.debug(f"Email with subject '{subject_str}' filtered out: no whitelist keywords found in subject.")
                return False

        # Subject Keywords Blacklist Check
        if settings.email_subject_keywords_blacklist:
            if any(keyword in subject_str_lower for keyword in settings.email_subject_keywords_blacklist):
                logger.debug(f"Email with subject '{subject_str}' filtered out: blacklist keyword found in subject.")
                return False
        
        return True

    def connect(self) -> bool:
        """Connect to the IMAP server"""
        try:
            logger.info(f"Attempting to connect to IMAP server: {self.server}:{self.port} as {self.username}")
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
            self.connection.login(self.username, self.password)
            self.connection.select(self.folder)
            logger.info(f"Successfully connected to {self.server}:{self.port} and selected folder '{self.folder}'")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP connection error: {str(e)}")
            self.connection = None # Ensure connection is None on failure
            return False
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {str(e)}")
            self.connection = None # Ensure connection is None on failure
            return False

    def disconnect(self) -> None:
        """Disconnect from the IMAP server"""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
                logger.info("Successfully disconnected from IMAP server.")
            except Exception as e:
                logger.error(f"Error during IMAP disconnect: {str(e)}")
            finally:
                self.connection = None

    def get_unread_emails(self) -> List[dict]:
        """Retrieve unread emails"""
        if not self.connection:
            logger.error("Not connected to IMAP server. Call connect() first.")
            return []
        try:
            status, messages = self.connection.search(None, "UNSEEN")
            if status != "OK":
                logger.error(f"Failed to search emails: {status}")
                return []

            unread_emails = []
            email_ids = messages[0].split()
            if not email_ids:
                logger.info("No unread emails found.")
                return []
            
            logger.info(f"Found {len(email_ids)} unread emails.")

            for msg_num in email_ids:
                status, msg_data = self.connection.fetch(msg_num, "(RFC822)")
                if status != "OK":
                    logger.error(f"Failed to fetch email {msg_num.decode()}")
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                email_data = {
                    "id": msg_num.decode(),
                    "subject": self._decode_header(msg["Subject"]),
                    "from": self._decode_header(msg["From"]),
                    "to": self._decode_header(msg["To"]),
                    "date": self._parse_date(msg["Date"]),
                    "body_text": self._get_email_body(msg, prefer_html=False),
                    "body_html": self._get_email_body(msg, prefer_html=True),
                    "raw_message": msg # Store the raw message for further processing if needed
                }

                if self._is_email_relevant(subject_str=email_data['subject'], from_str=email_data['from']):
                    unread_emails.append(email_data)
                    logger.debug(f"Processed relevant email: ID={email_data['id']}, Subject='{email_data['subject']}'")
                else:
                    logger.info(f"Skipping irrelevant email: ID={email_data['id']}, Subject='{email_data['subject']}', From='{email_data['from']}'")
                    # Optionally, mark as read or move here if desired in the future
                    # self.mark_as_read(email_data['id']) # Example: mark as read
                    pass

            return unread_emails

        except Exception as e:
            logger.error(f"Error retrieving emails: {str(e)}")
            return []

    def mark_as_read(self, email_id: str) -> bool:
        """Mark an email as read (seen)"""
        if not self.connection:
            logger.error("Not connected to IMAP server. Call connect() first.")
            return False
        try:
            result = self.connection.store(email_id.encode(), '+FLAGS', r'(\Seen)')
            if result[0] == 'OK':
                logger.info(f"Marked email {email_id} as read.")
                return True
            else:
                logger.error(f"Failed to mark email {email_id} as read. Server response: {result}")
                return False
        except Exception as e:
            logger.error(f"Error marking email {email_id} as read: {str(e)}")
            return False

    def _decode_header(self, header: Optional[str]) -> str:
        """Decode email headers (Subject, From, To)"""
        if not header:
            return ""
        
        decoded_parts = []
        try:
            for text, charset in decode_header(header):
                if isinstance(text, bytes):
                    try:
                        decoded_parts.append(text.decode(charset or 'utf-8', errors='replace'))
                    except (UnicodeDecodeError, LookupError): # LookupError for invalid charset
                        decoded_parts.append(text.decode('latin1', errors='replace')) # Fallback charset
                else:
                    decoded_parts.append(text)
            return "".join(decoded_parts)
        except Exception as e:
            logger.warning(f"Could not decode header: {header}. Error: {e}")
            return str(header) # Return original header as a string if decoding fails

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string from email header into datetime object"""
        if not date_str:
            return None
        try:
            dt = parsedate_to_datetime(date_str)
            return dt
        except Exception as e:
            logger.warning(f"Could not parse date string: {date_str}. Error: {e}")
            # Try a few common formats as a fallback
            common_formats = [
                "%a, %d %b %Y %H:%M:%S %z", 
                "%d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z"
            ]
            for fmt in common_formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            logger.error(f"Failed to parse date string '{date_str}' with all fallback formats.")
            return None

    def _get_email_body(self, msg: email.message.Message, prefer_html: bool = False) -> str:
        """Extract text or HTML body from an email message."""
        body_text = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    try:
                        content = payload.decode(charset, errors='replace')
                    except (UnicodeDecodeError, LookupError):
                        content = payload.decode('latin1', errors='replace') # Fallback charset
                    
                    if content_type == "text/plain":
                        body_text += content
                    elif content_type == "text/html":
                        body_html += content
        else: # Not a multipart message, just a single part.
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            try:
                content = payload.decode(charset, errors='replace')
            except (UnicodeDecodeError, LookupError):
                content = payload.decode('latin1', errors='replace') # Fallback charset
            
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                body_text = content
            elif content_type == "text/html":
                body_html = content
        
        if prefer_html and body_html:
            return body_html
        if body_text: # Prefer text if not preferring HTML or if HTML is empty
            return body_text
        if body_html: # Fallback to HTML if text is empty and HTML is not preferred but available
            # Convert HTML to text if only HTML is available and text is desired but prefer_html is false
            # This ensures we always try to return something readable.
            if not prefer_html:
                 soup = BeautifulSoup(body_html, 'html.parser')
                 return soup.get_text(separator='\n', strip=True)
            return body_html
        
        return "" # Should not happen for most emails

# Example Usage (for testing purposes, can be removed or moved to a test file later)
if __name__ == '__main__':
    logger.info("Starting email client test...")
    # Ensure .env file is loaded for settings
    # from dotenv import load_dotenv
    # load_dotenv() 
    # print(f"EMAIL_USERNAME: {settings.email_username}") # Check if settings are loaded

    if not all([settings.email_server, settings.email_port, settings.email_username, settings.email_password]):
        logger.error("Email credentials not found in .env file. Please set EMAIL_SERVER, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD.")
    else:
        email_client = EmailClient(
            server=settings.email_server,
            port=settings.email_port,
            username=settings.email_username,
            password=settings.email_password,
            folder=settings.email_folder
        )

        if email_client.connect():
            logger.info("Connection successful. Fetching unread emails...")
            unread_emails = email_client.get_unread_emails()
            if unread_emails:
                logger.info(f"Found {len(unread_emails)} unread emails:")
                for i, mail in enumerate(unread_emails):
                    logger.info(f"--- Email {i+1} ---")
                    logger.info(f"  ID: {mail['id']}")
                    logger.info(f"  From: {mail['from']}")
                    logger.info(f"  To: {mail['to']}")
                    logger.info(f"  Subject: {mail['subject']}")
                    logger.info(f"  Date: {mail['date']}")
                    # logger.info(f"  Body (Text):\n{mail['body_text'][:200]}...") # Print only first 200 chars
                    # logger.info(f"  Body (HTML):\n{mail['body_html'][:200]}...") # Print only first 200 chars
                    
                    # Example: Mark the first unread email as read
                    if i == 0:
                        # email_client.mark_as_read(mail['id'])
                        pass # Avoid marking as read during tests unless intended
            else:
                logger.info("No unread emails found.")
            
            email_client.disconnect()
        else:
            logger.error("Failed to connect to the email server.")
