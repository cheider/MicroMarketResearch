import time
import random
import requests


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
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.CLOVER_API_TOKEN}",
            "Accept": "application/json",
        })
        self._base_url = config.CLOVER_BASE_URL.rstrip("/")
        self._merchant_id = config.CLOVER_MERCHANT_ID

    def _url(self, path: str) -> str:
        return f"{self._base_url}/v3/merchants/{self._merchant_id}/{path.lstrip('/')}"

    def get(self, path: str, params: dict = None) -> dict:
        url = self._url(path)
        delay = 1.0
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
                )
            except requests.exceptions.Timeout as exc:
                raise CloverAPIError(0, f"Request timed out: {exc}") from exc
            except requests.exceptions.RequestException as exc:
                raise CloverAPIError(0, f"Request failed: {exc}") from exc

            if response.status_code == 429:
                if attempt == self.MAX_RETRIES - 1:
                    raise CloverRateLimitError()
                retry_after = float(response.headers.get("retry-after", delay))
                jitter = random.uniform(0, delay * 0.25)
                time.sleep(retry_after + jitter)
                delay = min(delay * 2, 60.0)
                continue

            if not response.ok:
                raise CloverAPIError(response.status_code, response.text[:200])

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
