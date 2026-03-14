"""
Base adapter contract for bridge sources.
"""
from abc import ABC, abstractmethod
from typing import Any

from rasad.models import Article


class BaseAdapter(ABC):
    """Base class for bridge adapters."""

    @abstractmethod
    def fetch(self, source_config: dict[str, Any], timeout: int = 10) -> list[Article]:
        """Fetch and normalize source items into Article objects."""

