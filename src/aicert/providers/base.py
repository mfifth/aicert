"""Base provider for LLM API calls."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseProvider(ABC):
    """Base class for LLM providers."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a response from the model."""
        raise NotImplementedError

    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs):
        """Generate a streaming response from the model."""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        raise NotImplementedError
