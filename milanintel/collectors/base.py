"""
Base collector class with common functionality.
"""

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

from ..config import Config
from ..storage import Storage
from ..models import Run

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Base class for all collectors."""

    def __init__(self, config: Config, storage: Storage, run: Run):
        """
        Initialize collector.

        Args:
            config: Configuration object
            storage: Storage instance
            run: Current run object
        """
        self.config = config
        self.storage = storage
        self.run = run
        self.artifacts_path = Path(config.get('storage.artifacts_path', 'artifacts/'))
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """
        Execute collection process.

        Returns:
            Dictionary with collection results
        """
        pass

    def rate_limit(self, seconds: float):
        """
        Sleep for rate limiting.

        Args:
            seconds: Seconds to sleep
        """
        if seconds > 0:
            self.logger.debug(f"Rate limiting: sleeping {seconds}s")
            time.sleep(seconds)

    def ensure_artifact_dir(self, *path_parts: str) -> Path:
        """
        Ensure artifact directory exists.

        Args:
            *path_parts: Path components

        Returns:
            Path object
        """
        path = self.artifacts_path.joinpath(*path_parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_artifact(self, content: str, *path_parts: str) -> str:
        """
        Save artifact to file.

        Args:
            content: Content to save
            *path_parts: Path components (relative to artifacts/)

        Returns:
            Relative path to saved file
        """
        full_path = self.artifacts_path.joinpath(*path_parts)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Return path relative to project root
        return str(full_path.relative_to(Path.cwd()))

    def save_binary_artifact(self, content: bytes, *path_parts: str) -> str:
        """
        Save binary artifact to file.

        Args:
            content: Binary content
            *path_parts: Path components

        Returns:
            Relative path to saved file
        """
        full_path = self.artifacts_path.joinpath(*path_parts)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, 'wb') as f:
            f.write(content)

        return str(full_path.relative_to(Path.cwd()))
