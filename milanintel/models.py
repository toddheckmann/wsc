"""
Data models for the intelligence collection system.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class RunStatus(Enum):
    """Status of a collection run."""
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class SourceType(Enum):
    """Type of data source."""
    WEB = "web"
    JOB = "job"
    AD_GOOGLE = "ad_google"
    AD_META = "ad_meta"
    EMAIL = "email"


@dataclass
class Run:
    """Represents a collection run."""
    id: Optional[int] = None
    started_at_utc: Optional[datetime] = None
    finished_at_utc: Optional[datetime] = None
    status: RunStatus = RunStatus.STARTED
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'started_at_utc': self.started_at_utc.isoformat() if self.started_at_utc else None,
            'finished_at_utc': self.finished_at_utc.isoformat() if self.finished_at_utc else None,
            'status': self.status.value,
            'notes': self.notes
        }


@dataclass
class Observation:
    """Represents a single observed entity."""
    id: Optional[int] = None
    run_id: Optional[int] = None
    source: Optional[SourceType] = None
    entity_key: Optional[str] = None
    url: Optional[str] = None
    observed_at_utc: Optional[datetime] = None
    content_hash: Optional[str] = None
    raw_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    parsed_json: Optional[str] = None  # JSON string of parsed data
    status: str = "success"  # success, error, redirect
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'id': self.id,
            'run_id': self.run_id,
            'source': self.source.value if self.source else None,
            'entity_key': self.entity_key,
            'url': self.url,
            'observed_at_utc': self.observed_at_utc.isoformat() if self.observed_at_utc else None,
            'content_hash': self.content_hash,
            'raw_path': self.raw_path,
            'screenshot_path': self.screenshot_path,
            'parsed_json': self.parsed_json,
            'status': self.status,
            'error_message': self.error_message
        }


@dataclass
class WebPage:
    """Parsed web page data."""
    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    canonical_url: Optional[str] = None
    final_url: Optional[str] = None  # After redirects
    status_code: Optional[int] = None
    links: list = field(default_factory=list)
    h1_tags: list = field(default_factory=list)


@dataclass
class Job:
    """Parsed job listing data."""
    title: str
    location: Optional[str] = None
    department: Optional[str] = None
    employment_type: Optional[str] = None
    posted_date: Optional[str] = None
    description: Optional[str] = None
    url: str
    job_id: Optional[str] = None
    requisition_id: Optional[str] = None


@dataclass
class AdCreative:
    """Parsed ad creative data."""
    platform: str  # google, meta
    advertiser: str
    creative_id: Optional[str] = None
    text: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    media_urls: list = field(default_factory=list)
    landing_page: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    spend_info: Optional[Dict[str, Any]] = None
    targeting_info: Optional[Dict[str, Any]] = None


@dataclass
class Email:
    """Parsed email data."""
    message_id: str
    from_address: str
    from_domain: str
    to_address: str
    subject: str
    date: datetime
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    preheader: Optional[str] = None
    links: list = field(default_factory=list)
    attachments: list = field(default_factory=list)
    headers: Optional[Dict[str, str]] = None
