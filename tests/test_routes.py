import json
import pytest
from unittest.mock import MagicMock

import app.database as db_module


@pytest.fixture(autouse=True)
def setup_db(app):
    db_module._db_path = app.config["DB_PATH"]
    yield


class TestDashboardRoute:
    def test_returns_200(self, client):
        response = client.get("/", follow_redirects=True)
        assert response.status_code == 200

    def test_contains_expected_text(self, client):
        response = client.get("/", follow_redirects=True)
        assert b"NSC Micro Market" in response.data


class TestIngestStatusRoute:
    def test_returns_200_with_no_sync_history(self, client):
        response = client.get("/ingest/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "no_sync_found"


class TestIngestRoute:
    def test_ingest_with_mocked_client_creates_sync_log(self, client, app):
        mock_client = MagicMock()
        mock_client.get.return_value = {"elements": []}
        app.extensions["clover_client"] = mock_client

        response = client.post(
            "/ingest",
            data=json.dumps({"mode": "full", "days": 30}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

        status_response = client.get("/ingest/status")
        status_data = json.loads(status_response.data)
        assert status_data["status"] == "success"

    def test_ingest_defaults_to_incremental(self, client, app):
        mock_client = MagicMock()
        mock_client.get.return_value = {"elements": []}
        app.extensions["clover_client"] = mock_client

        response = client.post("/ingest", content_type="application/json")
        assert response.status_code == 200


class TestMarginsRoute:
    def test_returns_200(self, client):
        response = client.get("/analysis/margins")
        assert response.status_code == 200

    def test_accepts_threshold_param(self, client):
        response = client.get("/analysis/margins?threshold=0.20")
        assert response.status_code == 200


class TestShrinkageRoute:
    def test_returns_200(self, client):
        response = client.get("/analysis/shrinkage")
        assert response.status_code == 200

    def test_accepts_days_param(self, client):
        response = client.get("/analysis/shrinkage?days=7")
        assert response.status_code == 200


class TestVelocityRoute:
    def test_returns_200(self, client):
        response = client.get("/analysis/velocity")
        assert response.status_code == 200


class TestItemRoute:
    def test_unknown_item_returns_404(self, client):
        response = client.get("/item/nonexistent-id")
        assert response.status_code == 404


class TestSettingsRoute:
    def test_settings_returns_200(self, client):
        response = client.get("/settings")
        assert response.status_code == 200

    def test_settings_contains_form(self, client):
        response = client.get("/settings")
        assert b"clover_api_token" in response.data
        assert b"clover_merchant_id" in response.data

    def test_settings_post_updates_merchant_id(self, client, app):
        response = client.post(
            "/settings",
            data={
                "clover_api_token": "",
                "clover_merchant_id": "new-merchant-456",
                "clover_base_url_select": "https://api.clover.com",
                "clover_base_url_custom": "",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        cfg = app.extensions["app_config"]
        assert cfg.CLOVER_MERCHANT_ID == "new-merchant-456"

    def test_settings_post_blank_token_preserves_existing(self, client, app):
        original_token = app.extensions["app_config"].CLOVER_API_TOKEN
        client.post(
            "/settings",
            data={
                "clover_api_token": "",
                "clover_merchant_id": "test-merchant",
                "clover_base_url_select": "https://api.clover.com",
                "clover_base_url_custom": "",
            },
        )
        assert app.extensions["app_config"].CLOVER_API_TOKEN == original_token

    def test_settings_post_blank_merchant_id_rejected(self, client):
        response = client.post(
            "/settings",
            data={
                "clover_api_token": "",
                "clover_merchant_id": "",
                "clover_base_url_select": "https://api.clover.com",
                "clover_base_url_custom": "",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"cannot be blank" in response.data
