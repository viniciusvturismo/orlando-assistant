import logging
import time
from typing import Optional

import anthropic

from ...config import settings

logger = logging.getLogger(__name__)


class ClaudeClient:
    """
    Único ponto de contato com a Claude API.
    Centraliza retry, timeout e logging de latência.
    """

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._max_retries = 3
        self._timeout = 20.0

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1000,
    ) -> str:
        """
        Envia uma requisição à Claude API e retorna o texto da resposta.
        Lança exceção após esgotar retries.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            t0 = time.monotonic()
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                latency = round((time.monotonic() - t0) * 1000)
                logger.info("claude_api_ok attempt=%d latency_ms=%d", attempt, latency)
                return response.content[0].text

            except anthropic.RateLimitError as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning("claude_rate_limit attempt=%d waiting=%ds", attempt, wait)
                time.sleep(wait)

            except anthropic.APIError as e:
                last_error = e
                logger.error("claude_api_error attempt=%d error=%s", attempt, str(e))
                if attempt < self._max_retries:
                    time.sleep(1)

        raise RuntimeError(f"Claude API failed after {self._max_retries} attempts: {last_error}")


# Singleton — compartilhado por toda a aplicação
_client: Optional[ClaudeClient] = None


def get_claude_client() -> ClaudeClient:
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
