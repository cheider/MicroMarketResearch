import logging
import time
import random
import requests

from app.clover.query_params import prepare_query_params

logger = logging.getLogger(__name__)


class CloverAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Clover API error {status_code}: {message}")


class CloverRateLimitError(CloverAPIError):
    def __init__(self):
        super().__init__(429, "Rate limit exceeded after maximum retries")


class CloverClient:
    MAX_RETRIES = 5
    CONNECT_TIMEOUT = 30
    READ_TIMEOUT = 60

    def __init__(self, config):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.CLOVER_API_TOKEN}",
            "Accept": "application/json",
        })
        self._base_url = config.CLOVER_BASE_URL.rstrip("/")
        self._merchant_id = config.CLOVER_MERCHANT_ID

    def _url(self, path: str) -> str:
        return f"{self._base_url}/v3/merchants/{self._merchant_id}/{path.lstrip('/')}"

    def get_current_merchant(self) -> dict:
        """GET /v3/merchants/current — token resolves to the merchant (team smoke test)."""
        return self._request_json(f"{self._base_url}/v3/merchants/current")

    def get(self, path: str, params: dict | list | None = None) -> dict:
        return self._request_json(self._url(path), params=params)

    def _request_json(self, url: str, params: dict | list | None = None) -> dict:
        query = prepare_query_params(params)
        logger.debug("GET %s  params=%s", url, query)
        delay = 1.0
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.get(
                    url,
                    params=query,
                    timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
                )
            except requests.exceptions.Timeout as exc:
                logger.error("GET %s timed out: %s", url, exc)
                raise CloverAPIError(0, f"Request timed out: {exc}") from exc
            except requests.exceptions.RequestException as exc:
                logger.error("GET %s failed: %s", url, exc)
                raise CloverAPIError(0, f"Request failed: {exc}") from exc

            if response.status_code == 429:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error("GET %s  rate limit exceeded after %d attempts", url, self.MAX_RETRIES)
                    raise CloverRateLimitError()
                retry_after = float(response.headers.get("retry-after", delay))
                jitter = random.uniform(0, delay * 0.25)
                wait = retry_after + jitter
                logger.warning("GET %s  429 rate limit (attempt %d/%d), waiting %.1fs",
                               url, attempt + 1, self.MAX_RETRIES, wait)
                time.sleep(wait)
                delay = min(delay * 2, 60.0)
                continue

            if not response.ok:
                logger.error(
                    "GET %s  HTTP %d  body=%s",
                    url, response.status_code, response.text,
                )
                raise CloverAPIError(response.status_code, response.text[:200])

            logger.debug("GET %s  HTTP %d  bytes=%d", url, response.status_code, len(response.content))
            return response.json()

        raise CloverRateLimitError()

    def post(self, path: str, json: dict = None) -> dict:
        url = self._url(path)
        try:
            response = self._session.post(
                url,
                json=json,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
        except requests.exceptions.RequestException as exc:
            raise CloverAPIError(0, f"Request failed: {exc}") from exc

        if not response.ok:
            raise CloverAPIError(response.status_code, response.text[:200])

        return response.json()
