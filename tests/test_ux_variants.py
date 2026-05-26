"""UX variant presets — nav and Insights visibility."""

import pytest

from app.ux.variants import COOKIE_NAME, get_variant


@pytest.mark.parametrize("variant_id,insights_status", [
    ("team_main", 302),
    ("dashboards_plus", 302),
    ("insights_core", 200),
    ("insights_full", 200),
])
def test_insights_route_by_variant(client, variant_id, insights_status):
    client.set_cookie(COOKIE_NAME, variant_id)
    resp = client.get("/analysis/insights")
    assert resp.status_code == insights_status


def test_sales_always_200(client):
    for vid in ("team_main", "insights_full"):
        client.set_cookie(COOKIE_NAME, vid)
        assert client.get("/dashboards/sales").status_code == 200


def test_team_main_hides_insights_nav(client):
    client.set_cookie(COOKIE_NAME, "team_main")
    html = client.get("/dashboards/sales").data.decode()
    assert 'href="/analysis/insights"' not in html


def test_insights_full_shows_insights_nav(client):
    client.set_cookie(COOKIE_NAME, "insights_full")
    html = client.get("/dashboards/sales").data.decode()
    assert "/analysis/insights" in html


def test_period_presets_team_main(client):
    client.set_cookie(COOKIE_NAME, "team_main")
    html = client.get("/dashboards/sales").data.decode()
    assert "This Week" in html
    assert "Semester" not in html


def test_period_presets_full(client):
    client.set_cookie(COOKIE_NAME, "insights_full")
    html = client.get("/dashboards/sales").data.decode()
    assert "Semester" in html


def test_query_ux_overrides_cookie(client):
    client.set_cookie(COOKIE_NAME, "team_main")
    html = client.get("/dashboards/sales?ux=insights_full").data.decode()
    assert "Semester" in html
