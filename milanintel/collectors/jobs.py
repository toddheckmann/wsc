"""
Jobs collector for career page and job listings.
"""

import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from playwright.sync_api import sync_playwright, Browser, Page
from bs4 import BeautifulSoup

from ..models import Observation, SourceType, Job
from ..utils import normalize_html, compute_hash, slugify, make_entity_key
from .base import BaseCollector

logger = logging.getLogger(__name__)


class JobsCollector(BaseCollector):
    """Collector for job listings."""

    def collect(self) -> Dict[str, Any]:
        """
        Collect job listings from careers page.

        Returns:
            Dictionary with collection results
        """
        self.logger.info("Starting jobs collection")

        if not self.config.is_collector_enabled('jobs'):
            self.logger.info("Jobs collector is disabled")
            return {'status': 'disabled', 'observations': 0}

        careers_url = self.config.get('collectors.jobs.careers_url')
        if not careers_url:
            self.logger.warning("No careers URL configured")
            return {'status': 'no_url', 'observations': 0}

        rate_limit_seconds = self.config.get('collectors.jobs.rate_limit_seconds', 2.0)
        max_jobs = self.config.get('collectors.jobs.max_job_pages', 100)

        results = {
            'status': 'completed',
            'observations': 0,
            'jobs_found': 0,
            'errors': 0
        }

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.config.get('collectors.web.headless', True)
            )

            try:
                # Step 1: Collect careers page and extract job links
                job_urls = self._extract_job_links(browser, careers_url)
                results['jobs_found'] = len(job_urls)
                self.logger.info(f"Found {len(job_urls)} job listings")

                # Step 2: Collect each job detail page
                for i, job_url in enumerate(job_urls[:max_jobs]):
                    if i > 0:
                        self.rate_limit(rate_limit_seconds)

                    try:
                        observation = self._collect_job(browser, job_url)
                        results['observations'] += 1
                    except Exception as e:
                        self.logger.error(f"Error collecting job {job_url}: {e}")
                        results['errors'] += 1

            finally:
                browser.close()

        self.logger.info(
            f"Jobs collection completed: {results['observations']} jobs collected, "
            f"{results['errors']} errors"
        )

        return results

    def _extract_job_links(self, browser: Browser, careers_url: str) -> List[str]:
        """
        Extract job listing links from careers page.

        Args:
            browser: Playwright browser
            careers_url: Careers page URL

        Returns:
            List of job detail URLs
        """
        self.logger.info(f"Extracting job links from {careers_url}")

        context = browser.new_context()
        page = context.new_page()

        job_urls: Set[str] = set()

        try:
            page.goto(careers_url, timeout=30000, wait_until='networkidle')
            html = page.content()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Try multiple selectors from config
            selectors = self.config.get('collectors.jobs.selectors.job_links', '')
            if selectors:
                selector_list = [s.strip() for s in selectors.split(',')]
            else:
                # Default selectors to try
                selector_list = [
                    'a.job-listing',
                    '.career-opportunity a',
                    '.job-post a',
                    'a[href*="/job/"]',
                    'a[href*="/careers/"]',
                    'a[href*="/position/"]',
                    '.jobs-list a',
                    '[data-job-id]',
                ]

            # Try each selector
            for selector in selector_list:
                try:
                    links = soup.select(selector)
                    for link in links:
                        href = link.get('href')
                        if href:
                            # Make absolute URL
                            if href.startswith('/'):
                                from urllib.parse import urljoin
                                href = urljoin(careers_url, href)
                            elif not href.startswith('http'):
                                continue

                            # Filter out non-job links
                            if self._looks_like_job_url(href):
                                job_urls.add(href)
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")

            # If no jobs found with CSS selectors, try finding links heuristically
            if not job_urls:
                self.logger.info("No jobs found with selectors, trying heuristic approach")
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href.startswith('/'):
                        from urllib.parse import urljoin
                        href = urljoin(careers_url, href)

                    if self._looks_like_job_url(href):
                        # Check if link text suggests it's a job
                        text = link.get_text(strip=True).lower()
                        if text and len(text) > 5 and not text in ['home', 'about', 'contact']:
                            job_urls.add(href)

        finally:
            page.close()
            context.close()

        return list(job_urls)

    def _looks_like_job_url(self, url: str) -> bool:
        """Check if URL looks like a job listing."""
        url_lower = url.lower()
        job_patterns = [
            '/job/', '/jobs/', '/career/', '/careers/',
            '/position/', '/positions/', '/opening/', '/openings/',
            'requisition', 'posting', 'opportunity'
        ]
        return any(pattern in url_lower for pattern in job_patterns)

    def _collect_job(self, browser: Browser, job_url: str) -> Observation:
        """
        Collect a single job detail page.

        Args:
            browser: Playwright browser
            job_url: Job detail URL

        Returns:
            Observation object
        """
        self.logger.info(f"Collecting job: {job_url}")

        context = browser.new_context()
        page = context.new_page()

        observation = Observation(
            run_id=self.run.id,
            source=SourceType.JOB,
            url=job_url,
            observed_at_utc=datetime.utcnow(),
            status='success'
        )

        try:
            page.goto(job_url, timeout=30000, wait_until='networkidle')
            html = page.content()

            # Parse job data
            job_data = self._parse_job(html, job_url)

            # Create stable job key
            job_key = self._make_job_key(job_data, job_url)
            observation.entity_key = job_key

            # Compute content hash
            normalized = normalize_html(html)
            content_hash = compute_hash(normalized)
            observation.content_hash = content_hash

            # Save artifacts
            date_str = datetime.utcnow().strftime('%Y-%m-%d')
            job_slug = slugify(job_data.title)[:50]  # Limit length

            # Save HTML
            raw_path = self.save_artifact(
                html,
                'jobs', date_str, job_slug, 'detail.html'
            )
            observation.raw_path = raw_path

            # Take screenshot
            screenshot_bytes = page.screenshot(full_page=True, type='png')
            screenshot_path = self.save_binary_artifact(
                screenshot_bytes,
                'jobs', date_str, job_slug, 'screenshot.png'
            )
            observation.screenshot_path = screenshot_path

            # Save parsed data
            parsed_json = json.dumps(job_data.__dict__, indent=2, default=str)
            observation.parsed_json = parsed_json

            self.save_artifact(
                parsed_json,
                'jobs', date_str, job_slug, 'parsed.json'
            )

            self.logger.info(
                f"Collected job: {job_data.title} @ {job_data.location}"
            )

        except Exception as e:
            self.logger.error(f"Error collecting job {job_url}: {e}")
            observation.status = 'error'
            observation.error_message = str(e)
            observation.entity_key = make_entity_key(job_url)

        finally:
            page.close()
            context.close()

        # Save observation
        self.storage.create_observation(observation)

        return observation

    def _parse_job(self, html: str, url: str) -> Job:
        """
        Parse job detail page HTML.

        Args:
            html: HTML content
            url: Job URL

        Returns:
            Job object
        """
        soup = BeautifulSoup(html, 'lxml')
        selectors = self.config.get('collectors.jobs.selectors', {})

        # Extract title
        title = self._extract_with_selectors(
            soup,
            selectors.get('title', 'h1, .job-title, [data-job-title]')
        )

        # Extract location
        location = self._extract_with_selectors(
            soup,
            selectors.get('location', '.job-location, .location, [data-location]')
        )

        # Extract department
        department = self._extract_with_selectors(
            soup,
            selectors.get('department', '.job-department, .department')
        )

        # Extract employment type
        employment_type = self._extract_with_selectors(
            soup,
            selectors.get('employment_type', '.job-type, .employment-type')
        )

        # Extract posted date
        posted_date = self._extract_with_selectors(
            soup,
            selectors.get('posted_date', '.job-posted, .posted-date, time')
        )

        # Extract description
        description = self._extract_with_selectors(
            soup,
            selectors.get('description', '.job-description, .description, .job-content'),
            get_html=True
        )

        # Try to extract job ID from URL or HTML
        job_id = self._extract_job_id(url, soup)
        requisition_id = self._extract_requisition_id(url, soup)

        return Job(
            title=title or "Unknown Position",
            location=location,
            department=department,
            employment_type=employment_type,
            posted_date=posted_date,
            description=description,
            url=url,
            job_id=job_id,
            requisition_id=requisition_id
        )

    def _extract_with_selectors(
        self,
        soup: BeautifulSoup,
        selectors: str,
        get_html: bool = False
    ) -> Optional[str]:
        """Extract content using CSS selectors."""
        selector_list = [s.strip() for s in selectors.split(',')]

        for selector in selector_list:
            try:
                element = soup.select_one(selector)
                if element:
                    if get_html:
                        return str(element)
                    else:
                        return element.get_text(strip=True)
            except Exception:
                continue

        return None

    def _extract_job_id(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Extract job ID from URL or HTML."""
        # Try URL patterns
        patterns = [
            r'/job/(\d+)',
            r'/jobs/(\d+)',
            r'id=(\d+)',
            r'job_id=(\w+)',
            r'/(\d+)/?$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Try HTML attributes
        for attr in ['data-job-id', 'data-id', 'id']:
            element = soup.find(attrs={attr: True})
            if element:
                return element.get(attr)

        return None

    def _extract_requisition_id(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Extract requisition ID from URL or HTML."""
        # Look for requisition patterns
        patterns = [
            r'req[uisition]*[_-]?(\w+)',
            r'posting[_-]?(\w+)',
        ]

        combined = url + ' ' + soup.get_text()

        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _make_job_key(self, job: Job, url: str) -> str:
        """
        Create stable job key.

        Prefer requisition ID > job ID > hash of title+location+url
        """
        if job.requisition_id:
            return f"req_{job.requisition_id}"
        elif job.job_id:
            return f"job_{job.job_id}"
        else:
            return make_entity_key(job.title, job.location or '', url)
