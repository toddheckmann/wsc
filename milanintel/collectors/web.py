"""
Web page collector using Playwright for dynamic content.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from ..models import Observation, SourceType, WebPage
from ..utils import normalize_html, compute_hash, slugify, extract_links
from .base import BaseCollector
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebCollector(BaseCollector):
    """Collector for web pages with screenshots."""

    def collect(self) -> Dict[str, Any]:
        """
        Collect web pages defined in configuration.

        Returns:
            Dictionary with collection results
        """
        self.logger.info("Starting web collection")

        if not self.config.is_collector_enabled('web'):
            self.logger.info("Web collector is disabled")
            return {'status': 'disabled', 'observations': 0}

        urls = self.config.get('collectors.web.urls', [])
        if not urls:
            self.logger.warning("No URLs configured for web collection")
            return {'status': 'no_urls', 'observations': 0}

        rate_limit_seconds = self.config.get('collectors.web.rate_limit_seconds', 2.0)
        results = {
            'status': 'completed',
            'observations': 0,
            'errors': 0,
            'pages': []
        }

        # Use Playwright to collect pages
        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright)

            try:
                for i, url_config in enumerate(urls):
                    if i > 0:
                        self.rate_limit(rate_limit_seconds)

                    try:
                        observation = self._collect_page(browser, url_config)
                        results['observations'] += 1
                        results['pages'].append({
                            'url': url_config['url'],
                            'slug': url_config.get('slug', ''),
                            'status': observation.status
                        })
                    except Exception as e:
                        self.logger.error(f"Error collecting {url_config['url']}: {e}")
                        results['errors'] += 1
                        results['pages'].append({
                            'url': url_config['url'],
                            'slug': url_config.get('slug', ''),
                            'status': 'error',
                            'error': str(e)
                        })

            finally:
                browser.close()

        self.logger.info(
            f"Web collection completed: {results['observations']} pages, "
            f"{results['errors']} errors"
        )

        return results

    def _launch_browser(self, playwright) -> Browser:
        """Launch browser with configured options."""
        headless = self.config.get('collectors.web.headless', True)
        user_agent = self.config.get('collectors.web.user_agent')

        browser = playwright.chromium.launch(headless=headless)
        self.logger.debug(f"Launched browser (headless={headless})")

        return browser

    def _collect_page(self, browser: Browser, url_config: Dict[str, str]) -> Observation:
        """
        Collect a single web page.

        Args:
            browser: Playwright browser instance
            url_config: URL configuration dict with 'url' and 'slug'

        Returns:
            Observation object
        """
        url = url_config['url']
        slug = url_config.get('slug', slugify(url))

        self.logger.info(f"Collecting web page: {url}")

        # Create context and page
        context = browser.new_context(
            viewport={
                'width': self.config.get('collectors.web.viewport_width', 1920),
                'height': self.config.get('collectors.web.viewport_height', 1080)
            },
            user_agent=self.config.get('collectors.web.user_agent')
        )

        page = context.new_page()
        timeout = self.config.get('collectors.web.timeout_ms', 30000)

        observation = Observation(
            run_id=self.run.id,
            source=SourceType.WEB,
            entity_key=slugify(url),
            url=url,
            observed_at_utc=datetime.utcnow(),
            status='success'
        )

        try:
            # Navigate to page
            response = page.goto(url, timeout=timeout, wait_until='networkidle')

            if response is None:
                raise Exception("No response received")

            # Check for redirects
            final_url = page.url
            if final_url != url:
                self.logger.info(f"Redirect detected: {url} -> {final_url}")
                observation.status = 'redirect'

            # Get HTML content
            html_content = page.content()

            # Parse page data
            parsed_data = self._parse_page(html_content, final_url, response.status)

            # Normalize HTML for hashing
            normalized_html = normalize_html(html_content)
            content_hash = compute_hash(normalized_html)

            observation.content_hash = content_hash

            # Save artifacts
            date_str = datetime.utcnow().strftime('%Y-%m-%d')
            artifact_dir = self.ensure_artifact_dir('web', date_str, slug)

            # Save raw HTML
            raw_path = self.save_artifact(
                html_content,
                'web', date_str, slug, 'page.html'
            )
            observation.raw_path = raw_path

            # Take screenshot (full page)
            screenshot_bytes = page.screenshot(full_page=True, type='png')
            screenshot_path = self.save_binary_artifact(
                screenshot_bytes,
                'web', date_str, slug, 'screenshot.png'
            )
            observation.screenshot_path = screenshot_path

            # Save parsed data
            parsed_json = json.dumps(parsed_data.__dict__, indent=2, default=str)
            observation.parsed_json = parsed_json

            self.save_artifact(
                parsed_json,
                'web', date_str, slug, 'parsed.json'
            )

            self.logger.info(
                f"Collected {url}: hash={content_hash[:8]}, "
                f"status={parsed_data.status_code}"
            )

            # Check for changes
            if self.storage.check_for_changes(observation.entity_key, content_hash):
                self.logger.info(f"Content changed for {url}")
            else:
                self.logger.info(f"No changes detected for {url}")

        except PlaywrightTimeout as e:
            self.logger.error(f"Timeout collecting {url}: {e}")
            observation.status = 'error'
            observation.error_message = f"Timeout: {str(e)}"

        except Exception as e:
            self.logger.error(f"Error collecting {url}: {e}")
            observation.status = 'error'
            observation.error_message = str(e)

        finally:
            page.close()
            context.close()

        # Save observation to database
        self.storage.create_observation(observation)

        return observation

    def _parse_page(self, html: str, url: str, status_code: int) -> WebPage:
        """
        Parse web page HTML to extract structured data.

        Args:
            html: HTML content
            url: Page URL
            status_code: HTTP status code

        Returns:
            WebPage object
        """
        soup = BeautifulSoup(html, 'lxml')

        # Extract title
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else None

        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc.get('content') if meta_desc else None

        # Extract canonical URL
        canonical = soup.find('link', attrs={'rel': 'canonical'})
        canonical_url = canonical.get('href') if canonical else None

        # Extract all H1 tags
        h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all('h1')]

        # Extract links
        links = extract_links(soup, url)

        return WebPage(
            url=url,
            title=title,
            meta_description=description,
            canonical_url=canonical_url,
            final_url=url,
            status_code=status_code,
            links=links[:100],  # Limit to 100 links
            h1_tags=h1_tags
        )
