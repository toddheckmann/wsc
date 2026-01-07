"""
Ads collector with pluggable backends for Google and Meta ad libraries.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from ..models import Observation, SourceType, AdCreative
from ..utils import compute_hash, make_entity_key
from .base import BaseCollector

logger = logging.getLogger(__name__)


class AdProvider(ABC):
    """Base class for ad data providers."""

    @abstractmethod
    def fetch_ads(self) -> List[AdCreative]:
        """
        Fetch ad creatives.

        Returns:
            List of AdCreative objects
        """
        pass


class ManualExportProvider(AdProvider):
    """
    Provider that reads manually exported JSON/CSV files.

    Files should be dropped into the import_path directory.
    Expected format: JSON array of ad objects or CSV with headers.
    """

    def __init__(self, platform: str, import_path: str, advertiser_name: str):
        self.platform = platform
        self.import_path = Path(import_path)
        self.advertiser_name = advertiser_name
        self.logger = logging.getLogger(f"{__name__}.ManualExportProvider")

    def fetch_ads(self) -> List[AdCreative]:
        """Read ads from import directory."""
        self.import_path.mkdir(parents=True, exist_ok=True)

        ads = []

        # Look for JSON files
        json_files = list(self.import_path.glob('*.json'))

        if not json_files:
            self.logger.warning(
                f"No JSON files found in {self.import_path}. "
                f"Drop exported ad data here to import."
            )
            return []

        for json_file in json_files:
            self.logger.info(f"Reading ads from {json_file.name}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Handle different JSON structures
                if isinstance(data, list):
                    ad_list = data
                elif isinstance(data, dict) and 'ads' in data:
                    ad_list = data['ads']
                elif isinstance(data, dict) and 'data' in data:
                    ad_list = data['data']
                else:
                    self.logger.warning(f"Unknown JSON structure in {json_file.name}")
                    continue

                # Parse each ad
                for ad_data in ad_list:
                    try:
                        ad = self._parse_ad(ad_data)
                        if ad:
                            ads.append(ad)
                    except Exception as e:
                        self.logger.error(f"Error parsing ad: {e}")

            except Exception as e:
                self.logger.error(f"Error reading {json_file.name}: {e}")

        self.logger.info(f"Loaded {len(ads)} ads from {len(json_files)} files")
        return ads

    def _parse_ad(self, data: Dict[str, Any]) -> Optional[AdCreative]:
        """Parse ad data from JSON."""
        # Flexible parsing based on platform
        if self.platform == 'google':
            return self._parse_google_ad(data)
        elif self.platform == 'meta':
            return self._parse_meta_ad(data)
        else:
            return self._parse_generic_ad(data)

    def _parse_google_ad(self, data: Dict[str, Any]) -> Optional[AdCreative]:
        """Parse Google Ads Transparency Center export."""
        return AdCreative(
            platform='google',
            advertiser=data.get('advertiser_name', self.advertiser_name),
            creative_id=data.get('creative_id') or data.get('ad_id'),
            text=data.get('ad_text') or data.get('text'),
            headline=data.get('headline'),
            description=data.get('description'),
            media_urls=data.get('media_urls', []) or [data.get('image_url')],
            landing_page=data.get('landing_page') or data.get('destination_url'),
            first_seen=data.get('first_seen') or data.get('start_date'),
            last_seen=data.get('last_seen') or data.get('end_date'),
            spend_info=data.get('spend'),
            targeting_info=data.get('targeting')
        )

    def _parse_meta_ad(self, data: Dict[str, Any]) -> Optional[AdCreative]:
        """Parse Meta Ad Library export."""
        # Handle nested structure
        if 'snapshot' in data:
            snapshot = data['snapshot']
        else:
            snapshot = data

        media_urls = []
        if 'images' in snapshot:
            media_urls.extend(snapshot['images'])
        if 'videos' in snapshot:
            media_urls.extend(snapshot['videos'])
        if 'cards' in snapshot:
            for card in snapshot.get('cards', []):
                if 'image' in card:
                    media_urls.append(card['image'])

        return AdCreative(
            platform='meta',
            advertiser=data.get('page_name', self.advertiser_name),
            creative_id=data.get('ad_archive_id') or data.get('id'),
            text=snapshot.get('body_text') or snapshot.get('text'),
            headline=snapshot.get('title') or snapshot.get('link_title'),
            description=snapshot.get('link_description'),
            media_urls=media_urls,
            landing_page=snapshot.get('link_url') or snapshot.get('link_caption'),
            first_seen=data.get('ad_creation_time') or data.get('start_date'),
            last_seen=data.get('ad_delivery_stop_time'),
            spend_info={
                'spend': data.get('spend'),
                'currency': data.get('currency')
            } if data.get('spend') else None,
            targeting_info=data.get('target')
        )

    def _parse_generic_ad(self, data: Dict[str, Any]) -> Optional[AdCreative]:
        """Parse generic ad format."""
        return AdCreative(
            platform=self.platform,
            advertiser=data.get('advertiser', self.advertiser_name),
            creative_id=data.get('id') or data.get('creative_id'),
            text=data.get('text') or data.get('body'),
            headline=data.get('headline') or data.get('title'),
            description=data.get('description'),
            media_urls=data.get('media_urls', []),
            landing_page=data.get('landing_page') or data.get('url'),
            first_seen=data.get('first_seen'),
            last_seen=data.get('last_seen')
        )


class APIStubProvider(AdProvider):
    """
    Stub provider for API-based collection.

    This is a placeholder for future API integration.
    """

    def __init__(self, platform: str, config: Dict[str, Any]):
        self.platform = platform
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.APIStubProvider")

    def fetch_ads(self) -> List[AdCreative]:
        """Placeholder for API-based collection."""
        self.logger.warning(
            f"API provider for {self.platform} is not implemented. "
            f"This is a stub. Please use 'manual_export' provider "
            f"and drop exported data into the import directory."
        )
        # TODO: Implement API-based collection
        # For Google: Use Google Ads API or scrape Transparency Center
        # For Meta: Use Meta Ad Library API (requires access token)
        return []


class AdsCollector(BaseCollector):
    """Collector for advertising creatives from multiple platforms."""

    def collect(self) -> Dict[str, Any]:
        """
        Collect ads from configured platforms.

        Returns:
            Dictionary with collection results
        """
        self.logger.info("Starting ads collection")

        if not self.config.is_collector_enabled('ads'):
            self.logger.info("Ads collector is disabled")
            return {'status': 'disabled', 'observations': 0}

        platforms = self.config.get('collectors.ads.platforms', {})
        if not platforms:
            self.logger.warning("No ad platforms configured")
            return {'status': 'no_platforms', 'observations': 0}

        results = {
            'status': 'completed',
            'observations': 0,
            'platforms': {}
        }

        # Collect from each platform
        for platform_name, platform_config in platforms.items():
            if not platform_config.get('enabled', False):
                self.logger.info(f"Platform {platform_name} is disabled")
                continue

            try:
                platform_results = self._collect_platform(platform_name, platform_config)
                results['platforms'][platform_name] = platform_results
                results['observations'] += platform_results['observations']
            except Exception as e:
                self.logger.error(f"Error collecting ads from {platform_name}: {e}")
                results['platforms'][platform_name] = {
                    'status': 'error',
                    'error': str(e),
                    'observations': 0
                }

        self.logger.info(
            f"Ads collection completed: {results['observations']} ads collected"
        )

        return results

    def _collect_platform(
        self,
        platform_name: str,
        platform_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Collect ads from a single platform.

        Args:
            platform_name: Platform name (google, meta)
            platform_config: Platform configuration

        Returns:
            Collection results
        """
        self.logger.info(f"Collecting ads from {platform_name}")

        # Create provider
        provider_type = platform_config.get('provider', 'manual_export')

        if provider_type == 'manual_export':
            provider = ManualExportProvider(
                platform=platform_name,
                import_path=platform_config.get('import_path', f'imports/{platform_name}_ads/'),
                advertiser_name=platform_config.get('advertiser_name', 'Milan Laser')
            )
        elif provider_type == 'api_stub':
            provider = APIStubProvider(
                platform=platform_name,
                config=platform_config
            )
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

        # Fetch ads
        ads = provider.fetch_ads()

        results = {
            'status': 'completed',
            'observations': 0,
            'ads_count': len(ads)
        }

        # Save each ad as observation
        date_str = datetime.utcnow().strftime('%Y-%m-%d')

        for ad in ads:
            try:
                observation = self._save_ad(ad, platform_name, date_str)
                results['observations'] += 1
            except Exception as e:
                self.logger.error(f"Error saving ad: {e}")

        return results

    def _save_ad(
        self,
        ad: AdCreative,
        platform: str,
        date_str: str
    ) -> Observation:
        """
        Save ad creative as observation.

        Args:
            ad: AdCreative object
            platform: Platform name
            date_str: Date string for file organization

        Returns:
            Observation object
        """
        # Determine source type
        if platform == 'google':
            source_type = SourceType.AD_GOOGLE
        elif platform == 'meta':
            source_type = SourceType.AD_META
        else:
            source_type = SourceType.AD_GOOGLE  # Default

        # Create entity key
        entity_key = make_entity_key(
            platform,
            ad.creative_id or '',
            ad.text or '',
            ad.headline or ''
        )

        # Compute content hash
        ad_json = json.dumps(ad.__dict__, sort_keys=True, default=str)
        content_hash = compute_hash(ad_json)

        observation = Observation(
            run_id=self.run.id,
            source=source_type,
            entity_key=entity_key,
            url=ad.landing_page,
            observed_at_utc=datetime.utcnow(),
            content_hash=content_hash,
            status='success'
        )

        # Save parsed data
        parsed_json = json.dumps(ad.__dict__, indent=2, default=str)
        observation.parsed_json = parsed_json

        # Save to file
        safe_id = (ad.creative_id or entity_key[:16]).replace('/', '_')
        json_path = self.save_artifact(
            parsed_json,
            'ads', date_str, platform, f'{safe_id}.json'
        )

        observation.raw_path = json_path

        # Save to database
        self.storage.create_observation(observation)

        self.logger.debug(f"Saved ad: {ad.creative_id} from {platform}")

        return observation
