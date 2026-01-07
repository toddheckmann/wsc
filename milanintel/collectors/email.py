"""
Email collector via IMAP for monitoring seed inboxes.
"""

import imaplib
import email
import json
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from bs4 import BeautifulSoup

from ..models import Observation, SourceType, Email as EmailModel
from ..utils import compute_hash, make_entity_key, extract_domain
from .base import BaseCollector

logger = logging.getLogger(__name__)


class EmailCollector(BaseCollector):
    """Collector for email monitoring via IMAP."""

    def collect(self) -> Dict[str, Any]:
        """
        Collect emails from configured IMAP accounts.

        Returns:
            Dictionary with collection results
        """
        self.logger.info("Starting email collection")

        if not self.config.is_collector_enabled('email'):
            self.logger.info("Email collector is disabled")
            return {'status': 'disabled', 'observations': 0}

        accounts = self.config.get('collectors.email.accounts', [])
        if not accounts:
            self.logger.warning("No email accounts configured")
            return {'status': 'no_accounts', 'observations': 0}

        results = {
            'status': 'completed',
            'observations': 0,
            'accounts': {}
        }

        # Collect from each account
        for account_config in accounts:
            account_name = account_config.get('name', 'default')
            try:
                account_results = self._collect_account(account_name)
                results['accounts'][account_name] = account_results
                results['observations'] += account_results['observations']
            except Exception as e:
                self.logger.error(f"Error collecting from {account_name}: {e}")
                results['accounts'][account_name] = {
                    'status': 'error',
                    'error': str(e),
                    'observations': 0
                }

        self.logger.info(
            f"Email collection completed: {results['observations']} emails collected"
        )

        return results

    def _collect_account(self, account_name: str) -> Dict[str, Any]:
        """
        Collect emails from a single account.

        Args:
            account_name: Account name from config

        Returns:
            Collection results
        """
        self.logger.info(f"Collecting emails from {account_name}")

        # Get account configuration
        email_config = self.config.get_email_config(account_name)

        # Validate required fields
        if not email_config.get('host') or not email_config.get('username'):
            raise ValueError(
                f"Missing IMAP configuration for {account_name}. "
                f"Set MILANINTEL_EMAIL_HOST and MILANINTEL_EMAIL_USERNAME environment variables."
            )

        if not email_config.get('password'):
            raise ValueError(
                f"Missing IMAP password for {account_name}. "
                f"Set MILANINTEL_EMAIL_PASSWORD environment variable."
            )

        results = {
            'status': 'completed',
            'observations': 0,
            'emails_found': 0
        }

        # Connect to IMAP server
        mail = self._connect_imap(email_config)

        try:
            # Select folder
            folder = email_config.get('folder', 'INBOX')
            mail.select(folder)

            # Search for emails since last run (or last 7 days for first run)
            search_criteria = self._build_search_criteria(email_config)
            _, message_numbers = mail.search(None, search_criteria)

            message_ids = message_numbers[0].split()
            results['emails_found'] = len(message_ids)
            self.logger.info(f"Found {len(message_ids)} emails matching criteria")

            # Fetch each email
            for msg_num in message_ids:
                try:
                    observation = self._fetch_email(mail, msg_num, email_config)
                    if observation:
                        results['observations'] += 1
                except Exception as e:
                    self.logger.error(f"Error fetching email {msg_num}: {e}")

        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

        return results

    def _connect_imap(self, config: Dict[str, Any]) -> imaplib.IMAP4_SSL:
        """
        Connect to IMAP server.

        Args:
            config: Email configuration

        Returns:
            IMAP connection
        """
        host = config['host']
        port = config.get('port', 993)
        use_ssl = config.get('use_ssl', True)

        self.logger.info(f"Connecting to IMAP server: {host}:{port}")

        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(config['username'], config['password'])

        self.logger.info("Successfully connected to IMAP server")
        return mail

    def _build_search_criteria(self, config: Dict[str, Any]) -> str:
        """
        Build IMAP search criteria based on filters.

        Args:
            config: Email configuration with filters

        Returns:
            IMAP search string
        """
        criteria_parts = []

        # Date filter (emails from last 7 days by default)
        since_date = datetime.utcnow() - timedelta(days=7)
        date_str = since_date.strftime('%d-%b-%Y')
        criteria_parts.append(f'SINCE {date_str}')

        # Filter by sender domains
        filters = config.get('filters', {})
        from_domains = filters.get('from_domains', [])

        if from_domains:
            # IMAP doesn't support OR directly, so we'll fetch all and filter in Python
            # For now, just use the date filter
            pass

        criteria = ' '.join(criteria_parts)
        self.logger.debug(f"IMAP search criteria: {criteria}")

        return criteria

    def _fetch_email(
        self,
        mail: imaplib.IMAP4_SSL,
        msg_num: bytes,
        config: Dict[str, Any]
    ) -> Optional[Observation]:
        """
        Fetch and parse a single email.

        Args:
            mail: IMAP connection
            msg_num: Message number
            config: Email configuration

        Returns:
            Observation or None
        """
        # Fetch email
        _, msg_data = mail.fetch(msg_num, '(RFC822)')
        email_body = msg_data[0][1]
        msg = email.message_from_bytes(email_body)

        # Parse email
        email_data = self._parse_email(msg)

        # Apply filters
        if not self._passes_filters(email_data, config.get('filters', {})):
            self.logger.debug(f"Email {email_data.message_id} filtered out")
            return None

        self.logger.info(f"Processing email: {email_data.subject}")

        # Create observation
        observation = Observation(
            run_id=self.run.id,
            source=SourceType.EMAIL,
            entity_key=make_entity_key(
                email_data.from_domain,
                email_data.subject,
                email_data.body_text[:100] if email_data.body_text else ''
            ),
            url=None,
            observed_at_utc=datetime.utcnow(),
            status='success'
        )

        # Compute content hash
        content_hash = compute_hash(
            f"{email_data.subject}|{email_data.body_text or email_data.body_html or ''}"
        )
        observation.content_hash = content_hash

        # Save artifacts
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        safe_subject = re.sub(r'[^\w\s-]', '', email_data.subject)[:50]
        safe_subject = safe_subject.replace(' ', '_')

        inbox_name = config.get('username', 'default').split('@')[0]

        # Save raw .eml file
        raw_path = self.save_binary_artifact(
            email_body,
            'email', date_str, inbox_name, f'{safe_subject}_{msg_num.decode()}.eml'
        )
        observation.raw_path = raw_path

        # Save HTML body if present
        if email_data.body_html:
            self.save_artifact(
                email_data.body_html,
                'email', date_str, inbox_name, f'{safe_subject}_{msg_num.decode()}_body.html'
            )

        # Save parsed data
        parsed_json = json.dumps(email_data.__dict__, indent=2, default=str)
        observation.parsed_json = parsed_json

        self.save_artifact(
            parsed_json,
            'email', date_str, inbox_name, f'{safe_subject}_{msg_num.decode()}_parsed.json'
        )

        # Save to database
        self.storage.create_observation(observation)

        return observation

    def _parse_email(self, msg: email.message.Message) -> EmailModel:
        """
        Parse email message.

        Args:
            msg: Email message object

        Returns:
            EmailModel object
        """
        # Decode headers
        from_address = self._decode_header(msg.get('From', ''))
        to_address = self._decode_header(msg.get('To', ''))
        subject = self._decode_header(msg.get('Subject', ''))
        message_id = msg.get('Message-ID', '')

        # Parse date
        date_str = msg.get('Date')
        try:
            date = parsedate_to_datetime(date_str) if date_str else datetime.utcnow()
        except Exception:
            date = datetime.utcnow()

        # Extract email address from "Name <email@domain.com>" format
        email_match = re.search(r'<(.+?)>', from_address)
        if email_match:
            from_email = email_match.group(1)
        else:
            from_email = from_address

        from_domain = extract_domain(f"http://{from_email.split('@')[1] if '@' in from_email else 'unknown'}")

        # Extract body
        body_text = None
        body_html = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain' and not body_text:
                    try:
                        body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                elif content_type == 'text/html' and not body_html:
                    try:
                        body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except Exception:
                        pass
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                if content_type == 'text/plain':
                    body_text = payload
                elif content_type == 'text/html':
                    body_html = payload
            except Exception:
                pass

        # Extract preheader from HTML
        preheader = self._extract_preheader(body_html) if body_html else None

        # Extract links
        links = self._extract_email_links(body_html or body_text or '')

        # Get headers
        headers = {k: self._decode_header(v) for k, v in msg.items()}

        return EmailModel(
            message_id=message_id,
            from_address=from_address,
            from_domain=from_domain,
            to_address=to_address,
            subject=subject,
            date=date,
            body_text=body_text,
            body_html=body_html,
            preheader=preheader,
            links=links,
            attachments=[],  # TODO: Extract attachments if needed
            headers=headers
        )

    def _decode_header(self, header_value: str) -> str:
        """Decode email header."""
        if not header_value:
            return ''

        decoded_parts = decode_header(header_value)
        decoded_str = ''

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_str += part.decode(encoding or 'utf-8', errors='ignore')
                except Exception:
                    decoded_str += part.decode('utf-8', errors='ignore')
            else:
                decoded_str += str(part)

        return decoded_str

    def _extract_preheader(self, html: str) -> Optional[str]:
        """Extract email preheader from HTML."""
        try:
            soup = BeautifulSoup(html, 'lxml')

            # Common preheader patterns
            preheader_selectors = [
                '.preheader',
                '[class*="preheader"]',
                '[style*="display:none"][style*="max-height:0"]',
                '[style*="mso-hide:all"]'
            ]

            for selector in preheader_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(strip=True)
                    if text and len(text) > 10:
                        return text[:200]

            return None
        except Exception:
            return None

    def _extract_email_links(self, content: str) -> List[str]:
        """Extract links from email content."""
        links = []

        # Try HTML parsing first
        try:
            soup = BeautifulSoup(content, 'lxml')
            for link in soup.find_all('a', href=True):
                links.append(link['href'])
        except Exception:
            pass

        # Fallback to regex
        if not links:
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            links = re.findall(url_pattern, content)

        return list(set(links))[:50]  # Limit to 50 unique links

    def _passes_filters(self, email_data: EmailModel, filters: Dict[str, Any]) -> bool:
        """
        Check if email passes configured filters.

        Args:
            email_data: Parsed email data
            filters: Filter configuration

        Returns:
            True if email passes filters
        """
        # Filter by sender domain
        from_domains = filters.get('from_domains', [])
        if from_domains:
            if not any(domain in email_data.from_domain for domain in from_domains):
                return False

        # Filter by subject keywords
        subject_keywords = filters.get('subject_keywords', [])
        if subject_keywords:
            subject_lower = email_data.subject.lower()
            if not any(keyword.lower() in subject_lower for keyword in subject_keywords):
                return False

        return True
