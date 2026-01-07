"""
Data collectors for various sources.
"""

from .base import BaseCollector
from .web import WebCollector
from .jobs import JobsCollector
from .ads import AdsCollector
from .email import EmailCollector

__all__ = [
    'BaseCollector',
    'WebCollector',
    'JobsCollector',
    'AdsCollector',
    'EmailCollector',
]
