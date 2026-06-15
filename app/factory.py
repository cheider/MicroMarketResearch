"""Flask application factory (imported by run.py and tests, not by CLI scripts)."""

from flask import Flask, g, request

from app.config import Config, TestConfig
from app.database import init_db
from app.clover.client import CloverClient
from app.ux.variants import COOKIE_NAME, get_variant, list_variants, resolve_variant_id
from app.analysis.category_resolution import (
    SUGGESTED_CATEGORIES_COOKIE,
    use_suggested_categories,
)
from app.demo_anonymize import DEMO_ANONYMIZE_COOKIE, use_demo_anonymize
from app.sync_status import get_last_sync
from app.auto_sync import start_auto_sync


def create_app(config=None):
    app = Flask(__name__)

    cfg = config or Config()
    app.secret_key = cfg.SECRET_KEY
    app.config["DB_PATH"] = cfg.DB_PATH
    app.config["MARGIN_ALERT_THRESHOLD"] = cfg.MARGIN_ALERT_THRESHOLD
    app.config["INGEST_LOOKBACK_DAYS"] = cfg.INGEST_LOOKBACK_DAYS
    app.config["AUTO_SYNC_INTERVAL_MINUTES"] = cfg.AUTO_SYNC_INTERVAL_MINUTES

    init_db(cfg.DB_PATH)

    client = CloverClient(cfg)
    app.extensions["clover_client"] = client
    app.extensions["app_config"] = cfg

    @app.before_request
    def _load_request_preferences():
        vid = resolve_variant_id(
            request.args.get("ux"),
            request.cookies.get(COOKIE_NAME),
            cfg.UX_VARIANT_DEFAULT,
        )
        g.ux_variant_id = vid
        g.ux = get_variant(vid)
        g.use_suggested_categories = use_suggested_categories(
            request.cookies.get(SUGGESTED_CATEGORIES_COOKIE)
        )
        g.demo_anonymize = use_demo_anonymize(
            request.cookies.get(DEMO_ANONYMIZE_COOKIE)
        )

    @app.context_processor
    def _inject_template_globals():
        last = get_last_sync()
        label = "Never synced"
        if last:
            ts = (last.get("sync_ts") or "")[:19].replace("T", " ")
            status = last.get("status") or "unknown"
            label = f"{ts} ({status})"
        auto_min = cfg.AUTO_SYNC_INTERVAL_MINUTES
        freshness = (
            f"Last synced: {label}. "
            "Pages refresh from the local database on each load; "
            "run Sync Now to pull from Clover."
        )
        if auto_min and auto_min > 0:
            freshness += f" Auto-sync every {auto_min} min is on."
        return {
            "ux": g.get("ux") or get_variant(cfg.UX_VARIANT_DEFAULT),
            "ux_variant_id": g.get("ux_variant_id") or cfg.UX_VARIANT_DEFAULT,
            "ux_variants": list_variants(),
            "use_suggested_categories": getattr(g, "use_suggested_categories", False),
            "demo_anonymize": getattr(g, "demo_anonymize", False),
            "last_sync_label": label,
            "data_freshness_note": freshness,
        }

    from app.routes.dashboard import dashboard_bp
    from app.routes.dashboards import dashboards_bp
    from app.routes.ingest import ingest_bp
    from app.routes.margins import margins_bp
    from app.routes.shrinkage import shrinkage_bp
    from app.routes.velocity import velocity_bp
    from app.routes.item import item_bp
    from app.routes.settings import settings_bp
    from app.routes.insights import insights_bp
    from app.routes.clover_tests import clover_tests_bp
    from app.routes.quarters import quarters_bp
    from app.routes.inventory_tools import inventory_tools_bp
    from app.routes.category_analysis import category_analysis_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(margins_bp)
    app.register_blueprint(shrinkage_bp)
    app.register_blueprint(velocity_bp)
    app.register_blueprint(item_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(clover_tests_bp)
    app.register_blueprint(quarters_bp)
    app.register_blueprint(inventory_tools_bp)
    app.register_blueprint(category_analysis_bp)

    if not isinstance(cfg, TestConfig):
        start_auto_sync(app)

    return app
