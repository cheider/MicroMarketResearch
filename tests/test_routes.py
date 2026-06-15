import json
import time
import pytest
from unittest.mock import MagicMock, patch

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

    def test_sidebar_hides_analysis_links_by_default(self, client):
        response = client.get("/dashboards/sales")
        assert response.status_code == 200
        assert b"/analysis/insights" not in response.data
        assert b"UI demo preset" not in response.data

    def test_sidebar_shows_analysis_links_with_insights_preset(self, client):
        client.set_cookie("mmr_ux_variant", "insights_full")
        response = client.get("/dashboards/sales")
        assert response.status_code == 200
        assert b"/analysis/insights" in response.data
        assert b"/analysis/margins" in response.data


class TestInsightsRoute:
    def test_insights_returns_200(self, client):
        client.set_cookie("mmr_ux_variant", "insights_full")
        response = client.get("/analysis/insights")
        assert response.status_code == 200

    def test_insights_accepts_period(self, client):
        client.set_cookie("mmr_ux_variant", "insights_full")
        response = client.get("/analysis/insights?period=30d")
        assert response.status_code == 200

    def test_insights_redirects_when_team_main(self, client):
        client.set_cookie("mmr_ux_variant", "team_main")
        response = client.get("/analysis/insights")
        assert response.status_code == 302


class TestIngestStatusRoute:
    def test_returns_200_with_no_sync_history(self, client):
        response = client.get("/ingest/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "no_sync_found"


class TestIngestRoute:
    def _wait_for_job(self, client, job_id, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/ingest/progress/{job_id}")
            data = json.loads(resp.data)
            if data["overall_status"] in ("done", "error"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_ingest_with_mocked_client_creates_sync_log(self, client, app):
        mock_client = MagicMock()
        mock_client.get.return_value = {"elements": []}
        app.extensions["clover_client"] = mock_client

        response = client.post(
            "/ingest",
            data=json.dumps({"mode": "full", "days": 30}),
            content_type="application/json",
        )
        assert response.status_code == 202
        data = json.loads(response.data)
        assert data["status"] == "started"
        assert "job_id" in data

        final = self._wait_for_job(client, data["job_id"])
        assert final["overall_status"] == "done"

        status_response = client.get("/ingest/status")
        status_data = json.loads(status_response.data)
        assert status_data["status"] == "success"

    def test_ingest_defaults_to_incremental(self, client, app):
        mock_client = MagicMock()
        mock_client.get.return_value = {"elements": []}
        app.extensions["clover_client"] = mock_client

        response = client.post("/ingest", content_type="application/json")
        assert response.status_code == 202
        data = json.loads(response.data)
        assert data["status"] == "started"
        # Wait for completion so the background thread releases the DB file
        self._wait_for_job(client, data["job_id"])


class TestIngestProgress:
    def _start_ingest(self, client, app, mode="full"):
        mock_client = MagicMock()
        mock_client.get.return_value = {"elements": []}
        app.extensions["clover_client"] = mock_client
        resp = client.post(
            "/ingest",
            data=json.dumps({"mode": mode, "days": 30}),
            content_type="application/json",
        )
        return json.loads(resp.data)["job_id"]

    def _wait_for_completion(self, client, job_id, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/ingest/progress/{job_id}")
            data = json.loads(resp.data)
            if data["overall_status"] in ("done", "error"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_progress_endpoint_returns_404_for_unknown_job(self, client):
        resp = client.get("/ingest/progress/nonexistent-job-id")
        assert resp.status_code == 404

    def test_progress_endpoint_returns_200_for_known_job(self, client, app):
        job_id = self._start_ingest(client, app)
        resp = client.get(f"/ingest/progress/{job_id}")
        assert resp.status_code == 200
        self._wait_for_completion(client, job_id)

    def test_progress_response_has_required_keys(self, client, app):
        job_id = self._start_ingest(client, app)
        data = json.loads(client.get(f"/ingest/progress/{job_id}").data)
        assert "job_id" in data
        assert "overall_status" in data
        assert "stages" in data
        assert "result" in data
        assert "error_message" in data
        self._wait_for_completion(client, job_id)

    def test_all_stages_present_in_response(self, client, app):
        expected = {
            "categories", "items", "orders",
            "line_items", "daily_sales", "stock", "log",
        }
        job_id = self._start_ingest(client, app)
        data = json.loads(client.get(f"/ingest/progress/{job_id}").data)
        assert set(data["stages"].keys()) == expected
        self._wait_for_completion(client, job_id)

    def test_job_completes_with_overall_status_done(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        assert final["overall_status"] == "done"

    def test_all_stages_done_when_job_complete(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        for stage_id, stage_data in final["stages"].items():
            assert stage_data["status"] == "done", (
                f"Stage {stage_id!r} is "
                f"{stage_data['status']!r}, expected 'done'"
            )

    def test_result_populated_when_done(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        assert final["result"] is not None
        assert "records_fetched" in final["result"]
        assert "categories_synced" in final["result"]

    def test_incremental_mode_job_completes(self, client, app):
        job_id = self._start_ingest(client, app, mode="incremental")
        final = self._wait_for_completion(client, job_id)
        assert final["overall_status"] == "done"

    def test_stage_counts_are_non_negative_integers_or_none(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        for stage_id, stage_data in final["stages"].items():
            count = stage_data["count"]
            assert count is None or (isinstance(count, int) and count >= 0), (
                f"Stage {stage_id!r} has invalid count: {count!r}"
            )

    def test_job_id_in_progress_response_matches_post_response(
        self, client, app
    ):
        job_id = self._start_ingest(client, app)
        prog = json.loads(client.get(f"/ingest/progress/{job_id}").data)
        assert prog["job_id"] == job_id
        self._wait_for_completion(client, job_id)

    def test_error_message_is_none_on_successful_job(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        assert final["error_message"] is None

    def test_stage_records_have_detail_field(self, client, app):
        job_id = self._start_ingest(client, app)
        final = self._wait_for_completion(client, job_id)
        for stage_id, stage_data in final["stages"].items():
            assert "detail" in stage_data, (
                f"Stage {stage_id!r} missing 'detail' key"
            )

    def test_order_cache_is_set_after_ingest(self, client, app):
        from app.etl.load import get_fetched_order_ids
        job_id = self._start_ingest(client, app)
        self._wait_for_completion(client, job_id)
        ids = get_fetched_order_ids()
        assert isinstance(ids, set)


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
    @pytest.fixture(autouse=True)
    def no_env_write(self, monkeypatch):
        """Prevent settings tests from writing to the real .env file."""
        monkeypatch.setattr("app.routes.settings.set_key", lambda *a, **kw: None)

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

    def test_settings_category_suggestions_toggle(self, client):
        resp = client.post(
            "/settings/category-suggestions",
            data={"use_suggested_categories": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers.get("Set-Cookie", "").startswith(
            "mmr_use_suggested_categories=1"
        )

    def test_settings_includes_stress_test_ui(self, client):
        response = client.get("/settings")
        assert b"Run stress tests" in response.data
        assert b"stressProfile" in response.data


class TestCloverStressRoutes:
    def _wait_for_job(self, client, job_id, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/api/clover-tests/progress/{job_id}")
            data = json.loads(resp.data)
            if data["overall_status"] in ("done", "error"):
                return data
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def test_profiles_list(self, client):
        resp = client.get("/api/clover-tests/profiles")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["profiles"]) == 3

    @patch("app.routes.clover_tests.run_stress_suite")
    def test_start_and_complete_stress_job(self, mock_run, client):
        mock_run.return_value = {
            "profile": "light",
            "profile_label": "Light",
            "results": [{"name": "health_battery", "status": "pass", "requests": 7}],
            "summary": {
                "all_pass": True,
                "passed": 1,
                "warnings": 0,
                "failed": 0,
                "total_requests": 7,
                "rate_limits_hit": 0,
                "total_duration_ms": 100,
                "total_checks": 1,
            },
        }
        resp = client.post(
            "/api/clover-tests/start",
            data=json.dumps({"profile": "light"}),
            content_type="application/json",
        )
        assert resp.status_code == 202
        job_id = json.loads(resp.data)["job_id"]

        final = self._wait_for_job(client, job_id)
        assert final["overall_status"] == "done"
        assert final["result"]["summary"]["all_pass"] is True

    def test_progress_unknown_job_404(self, client):
        resp = client.get("/api/clover-tests/progress/does-not-exist")
        assert resp.status_code == 404
