"""OpenAI-compatible provider for LLM API calls."""

import os
from typing import Any, Dict, Optional

import httpx

from aicert.providers.base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI-compatible provider implementation (e.g., local LLMs, proxy servers)."""

    DEFAULT_BASE_URL = "http://localhost:8000/v1"
    API_KEY_ENV = "OPENAI_COMPAT_API_KEY"

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)
        self.temperature = temperature
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from environment if not set."""
        if self._api_key is None:
            return os.environ.get(self.API_KEY_ENV)
        return self._api_key

    @api_key.setter
    def api_key(self, value: Optional[str]):
        self._api_key = value

    @property
    def base_url(self) -> str:
        """Get base URL for API calls."""
        if self._base_url is None:
            return self.DEFAULT_BASE_URL
        return self._base_url

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            headers = {}
            api_key = self.api_key
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),  # Longer timeout for local models
                headers=headers,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a response from an OpenAI-compatible endpoint."""
        client = await self._get_client()

        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }

        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to OpenAI-compatible API: {e}")

        if not response.is_success:
            status_code = response.status_code
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
            except Exception:
                error_msg = response.text

            if status_code in (429, 500, 502, 503, 504):
                from aicert.runner import RetriableError
                raise RetriableError(f"OpenAI-compatible API error ({status_code}): {error_msg}")
            else:
                raise ValueError(f"OpenAI-compatible API error ({status_code}): {error_msg}")

        result = response.json()

        # Ensure we have the expected structure
        return {
            "choices": result.get("choices", []),
            "usage": result.get("usage", {}),
            "raw": result,
        }

    async def generate_stream(self, prompt: str, **kwargs):
        """Generate a streaming response from an OpenAI-compatible endpoint."""
        client = await self._get_client()

        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": True,
        }

        try:
            async with client.stream("POST", url, json=payload) as response:
                if not response.is_success:
                    status_code = response.status_code
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get("error", {}).get("message", await response.aread())
                    except Exception:
                        error_msg = await response.aread()

                    if status_code in (429, 500, 502, 503, 504):
                        from aicert.runner import RetriableError
                        raise RetriableError(f"OpenAI-compatible API error ({status_code}): {error_msg}")
                    else:
                        raise ValueError(f"OpenAI-compatible API error ({status_code}): {error_msg}")

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = __import__("json").loads(data)
                            yield chunk
                        except Exception:
                            continue
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to OpenAI-compatible API: {e}")

    @property
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        return "openai-compatible"
