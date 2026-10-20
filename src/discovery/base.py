"""Base interface and exceptions for micro-influencer discovery sources."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.validation.models import InfluencerProfile

logger = get_logger("discovery.base")


class DiscoveryError(Exception):
    """Base exception for all influencer discovery errors."""

    def __init__(self, message: str, source: str = "unknown") -> None:
        super().__init__(f"[{source}] {message}")
        self.message = message
        self.source = source


class SourceUnavailableError(DiscoveryError):
    """Raised when a discovery source, API credential, or client library is unavailable."""
    pass


class QuotaExhaustedError(DiscoveryError):
    """Raised when an API rate limit or daily quota is exceeded."""
    pass


class InvalidResponseError(DiscoveryError):
    """Raised when an external source returns malformed or unexpected data."""
    pass


class BaseDiscoverySource(ABC):
    """Abstract base class defining the contract for influencer discovery sources."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.logger = get_logger(f"discovery.{source_name}")

    @abstractmethod
    def discover(self, **kwargs: Any) -> List[InfluencerProfile]:
        """
        Discover, fetch, and return a validated list of influencer profiles.

        Args:
            **kwargs: Source-specific parameters (e.g. query, limit, category, file_path).

        Returns:
            List[InfluencerProfile]: Normalized and validated influencer profiles.

        Raises:
            SourceUnavailableError: If credentials or data sources are unreachable.
            QuotaExhaustedError: If API limits are exceeded.
            InvalidResponseError: If responses cannot be parsed.
            DiscoveryError: For generic discovery failures.
        """
        raise NotImplementedError("Subclasses must implement discover()")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(source='{self.source_name}')>"

