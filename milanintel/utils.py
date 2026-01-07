"""
Utility functions for hashing, normalization, retries, and more.
"""

import hashlib
import re
import time
import logging
from typing import Optional, Callable, Any, TypeVar
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

T = TypeVar('T')


def compute_hash(content: str, algorithm: str = "sha256") -> str:
    """
    Compute a stable hash of content.

    Args:
        content: String content to hash
        algorithm: Hash algorithm (sha256, md5)

    Returns:
        Hex digest of the hash
    """
    if algorithm == "sha256":
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    elif algorithm == "md5":
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def normalize_html(html: str) -> str:
    """
    Normalize HTML for stable hashing by removing dynamic elements.

    Removes:
    - <script> and <style> tags
    - Comments
    - UTM parameters and tracking params
    - Timestamps and session IDs (common patterns)
    - Excessive whitespace

    Args:
        html: Raw HTML content

    Returns:
        Normalized HTML string
    """
    soup = BeautifulSoup(html, 'lxml')

    # Remove script and style tags
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()

    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove common tracking/dynamic attributes
    dynamic_attrs = [
        'data-timestamp',
        'data-session',
        'data-visitor-id',
        'data-analytics',
        'data-gtm',
        'data-ga',
    ]

    for attr in dynamic_attrs:
        for tag in soup.find_all(attrs={attr: True}):
            del tag[attr]

    # Clean up URLs in href and src attributes
    for tag in soup.find_all(['a', 'link'], href=True):
        tag['href'] = clean_url(tag['href'])

    for tag in soup.find_all(['img', 'script'], src=True):
        tag['src'] = clean_url(tag['src'])

    # Get normalized text
    normalized = str(soup)

    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'>\s+<', '><', normalized)

    return normalized.strip()


def clean_url(url: str) -> str:
    """
    Remove tracking parameters from URLs.

    Args:
        url: URL to clean

    Returns:
        Cleaned URL
    """
    # List of common tracking parameters
    tracking_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'gclid', 'fbclid', 'msclkid', '_ga', 'mc_cid', 'mc_eid',
        'sessionid', 'sid', 'timestamp', '_t', '_hsenc', '_hsmi',
    }

    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Filter out tracking parameters
        cleaned_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in tracking_params
        }

        # Rebuild URL
        new_query = urlencode(cleaned_params, doseq=True)
        cleaned = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            ''  # Remove fragment
        ))

        return cleaned
    except Exception as e:
        logger.warning(f"Error cleaning URL {url}: {e}")
        return url


def slugify(text: str) -> str:
    """
    Convert text to a filesystem-safe slug.

    Args:
        text: Text to slugify

    Returns:
        Slugified string
    """
    # Convert to lowercase
    text = text.lower()

    # Replace spaces and special chars with hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)

    # Remove leading/trailing hyphens
    text = text.strip('-')

    return text


def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_backoff: float = 2.0,
    max_backoff: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
) -> T:
    """
    Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to catch

    Returns:
        Return value of func

    Raises:
        Last exception if all attempts fail
    """
    attempt = 0
    backoff = initial_backoff
    last_exception = None

    while attempt < max_attempts:
        try:
            return func()
        except exceptions as e:
            attempt += 1
            last_exception = e

            if attempt >= max_attempts:
                logger.error(f"Failed after {max_attempts} attempts: {e}")
                raise

            logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)

            # Exponential backoff
            backoff = min(backoff * exponential_base, max_backoff)

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


def extract_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: URL to parse

    Returns:
        Domain name
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return ""


def extract_links(soup: BeautifulSoup, base_url: str = "") -> list:
    """
    Extract all links from a BeautifulSoup object.

    Args:
        soup: BeautifulSoup parsed HTML
        base_url: Base URL for resolving relative links

    Returns:
        List of URLs
    """
    links = []

    for tag in soup.find_all('a', href=True):
        href = tag['href']

        # Handle relative URLs
        if base_url and not href.startswith(('http://', 'https://', '//')):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)

        links.append(href)

    return list(set(links))  # Deduplicate


def truncate_text(text: str, max_length: int = 1000) -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."


def extract_text_content(html: str) -> str:
    """
    Extract clean text content from HTML.

    Args:
        html: HTML content

    Returns:
        Clean text
    """
    soup = BeautifulSoup(html, 'lxml')

    # Remove script and style tags
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()

    # Get text
    text = soup.get_text(separator=' ', strip=True)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def make_entity_key(*parts: str) -> str:
    """
    Create a stable entity key from multiple parts.

    Args:
        *parts: Parts to combine

    Returns:
        Entity key (hash of parts)
    """
    combined = "|".join(str(p) for p in parts if p)
    return compute_hash(combined, algorithm="sha256")[:32]


def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
