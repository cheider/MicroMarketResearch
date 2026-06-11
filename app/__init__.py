from flask import Flask

from app.config import Config
from app.database import init_db
from app.clover.client import CloverClient


def create_app(config=None):
    app = Flask(__name__)

    cfg = config or Config()
    app.secret_key = cfg.SECRET_KEY
    app.config["DB_PATH"] = cfg.DB_PATH
    app.config["MARGIN_ALERT_THRESHOLD"] = cfg.MARGIN_ALERT_THRESHOLD

    init_db(cfg.DB_PATH)

    client = CloverClient(cfg)
    app.extensions["clover_client"] = client
    app.extensions["app_config"] = cfg

    from app.routes.dashboard import dashboard_bp
    from app.routes.dashboards import dashboards_bp
    from app.routes.ingest import ingest_bp
    from app.routes.margins import margins_bp
    from app.routes.shrinkage import shrinkage_bp
    from app.routes.velocity import velocity_bp
    from app.routes.item import item_bp
    from app.routes.settings import settings_bp
    from app.routes.quarters import quarters_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(margins_bp)
    app.register_blueprint(shrinkage_bp)
    app.register_blueprint(velocity_bp)
    app.register_blueprint(item_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(quarters_bp)

    return app
