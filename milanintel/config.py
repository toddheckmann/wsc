"""
Configuration management for the intelligence collector.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager."""

    def __init__(self, config_path: str):
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config.yaml
        """
        self.config_path = Path(config_path)
        self.data: Dict[str, Any] = {}

        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(self.config_path, 'r') as f:
            self.data = yaml.safe_load(f)

        logger.info(f"Loaded configuration from {config_path}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.

        Args:
            key: Dot-notation key (e.g., 'collectors.web.enabled')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get value from environment variable.

        Args:
            key: Environment variable name
            default: Default value if not found

        Returns:
            Environment variable value
        """
        return os.environ.get(key, default)

    def is_collector_enabled(self, collector_name: str) -> bool:
        """
        Check if a collector is enabled.

        Args:
            collector_name: Name of collector (web, jobs, ads, email)

        Returns:
            True if enabled
        """
        return self.get(f'collectors.{collector_name}.enabled', False)

    def get_email_config(self, account_name: str = 'seed_account_1') -> Dict[str, Any]:
        """
        Get email configuration with environment variable substitution.

        Args:
            account_name: Name of email account

        Returns:
            Email configuration dictionary
        """
        # Get base config from YAML
        accounts = self.get('collectors.email.accounts', [])
        account_config = None

        for acc in accounts:
            if acc.get('name') == account_name:
                account_config = acc
                break

        if not account_config:
            raise ValueError(f"Email account '{account_name}' not found in config")

        # Override with environment variables
        return {
            'host': self.get_env('MILANINTEL_EMAIL_HOST'),
            'port': int(self.get_env('MILANINTEL_EMAIL_PORT', '993')),
            'username': self.get_env('MILANINTEL_EMAIL_USERNAME'),
            'password': self.get_env('MILANINTEL_EMAIL_PASSWORD'),
            'folder': self.get_env('MILANINTEL_EMAIL_FOLDER', 'INBOX'),
            'use_ssl': account_config.get('use_ssl', True),
            'filters': account_config.get('filters', {})
        }

    def get_retry_config(self) -> Dict[str, Any]:
        """Get retry configuration."""
        return {
            'max_attempts': self.get('retry.max_attempts', 3),
            'initial_backoff': self.get('retry.initial_backoff_seconds', 2.0),
            'max_backoff': self.get('retry.max_backoff_seconds', 30.0),
            'exponential_base': self.get('retry.exponential_base', 2.0)
        }
