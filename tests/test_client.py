import pytest
from unittest.mock import MagicMock, patch, call
from requests import Session

from app.clover.client import CloverClient, CloverRateLimitError, CloverAPIError
from app.config import TestConfig


@pytest.fixture
def cfg():
    return TestConfig()


@pytest.fixture
def clover_client(cfg):
    return CloverClient(cfg)


def make_response(status_code, json_data=None, headers=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = status_code < 400
    mock.json.return_value = json_data or {}
    mock.text = str(json_data or "")
    mock.headers = headers or {}
    return mock


class TestCloverClient:
    def test_authorization_header_present(self, clover_client):
        headers = clover_client._session.headers
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_token_value_in_header(self, clover_client):
        assert "test-token" in clover_client._session.headers["Authorization"]

    def test_successful_get_returns_data(self, clover_client):
        expected = {"elements": [{"id": "item-1"}]}
        with patch.object(clover_client._session, "get", return_value=make_response(200, expected)):
            result = clover_client.get("items")
        assert result == expected

    def test_two_429s_then_success_retries_correctly(self, clover_client):
        responses = [
            make_response(429, headers={"retry-after": "0"}),
            make_response(429, headers={"retry-after": "0"}),
            make_response(200, {"elements": []}),
        ]
        with patch.object(clover_client._session, "get", side_effect=responses):
            with patch("time.sleep"):
                result = clover_client.get("items")
        assert result == {"elements": []}

    def test_five_429s_raises_rate_limit_error(self, clover_client):
        responses = [make_response(429, headers={"retry-after": "0"})] * 5
        with patch.object(clover_client._session, "get", side_effect=responses):
            with patch("time.sleep"):
                with pytest.raises(CloverRateLimitError):
                    clover_client.get("items")

    def test_non_429_error_raises_api_error(self, clover_client):
        with patch.object(clover_client._session, "get", return_value=make_response(500, "Server error")):
            with pytest.raises(CloverAPIError) as exc_info:
                clover_client.get("items")
            assert exc_info.value.status_code == 500

    def test_url_construction(self, clover_client):
        expected_url = "https://apisandbox.dev.clover.com/v3/merchants/test-merchant/items"
        with patch.object(clover_client._session, "get", return_value=make_response(200, {})) as mock_get:
            clover_client.get("items")
            called_url = mock_get.call_args[0][0]
        assert called_url == expected_url
