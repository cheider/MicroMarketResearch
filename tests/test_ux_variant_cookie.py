from app.ux.variants import COOKIE_NAME


def test_settings_ux_sets_cookie(client):
    resp = client.post(
        "/settings/ux",
        data={"ux_variant": "dashboards_plus", "next": "/dashboards/sales"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    cookie = resp.headers.get("Set-Cookie", "")
    assert COOKIE_NAME in cookie
    assert "dashboards_plus" in cookie


def test_cookie_applied_on_next_request(client):
    client.post(
        "/settings/ux",
        data={"ux_variant": "insights_core", "next": "/dashboards/sales"},
        follow_redirects=True,
    )
    assert client.get("/analysis/insights").status_code == 200
