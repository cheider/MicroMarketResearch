import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass
class Config:
    CLOVER_API_TOKEN: str = field(
        default_factory=lambda: os.environ.get("CLOVER_API_TOKEN", "")
    )
    CLOVER_MERCHANT_ID: str = field(
        default_factory=lambda: os.environ.get("CLOVER_MERCHANT_ID", "")
    )
    CLOVER_BASE_URL: str = field(
        default_factory=lambda: os.environ.get("CLOVER_BASE_URL", "https://api.clover.com")
    )
    ORDER_ID_HASH_SALT: str = field(
        default_factory=lambda: os.environ.get("ORDER_ID_HASH_SALT", "")
    )
    FLASK_SECRET_KEY: str = field(default_factory=lambda: os.environ["FLASK_SECRET_KEY"])
    DB_PATH: str = field(
        default_factory=lambda: os.environ.get("DB_PATH", "analytics.db")
    )
    MARGIN_ALERT_THRESHOLD: float = field(
        default_factory=lambda: float(os.environ.get("MARGIN_ALERT_THRESHOLD", "0.10"))
    )
    SECRET_KEY: str = field(default_factory=lambda: os.environ.get("FLASK_SECRET_KEY", "dev"))


class TestConfig(Config):
    def __init__(self):
        object.__setattr__(self, "CLOVER_API_TOKEN", "test-token")
        object.__setattr__(self, "CLOVER_MERCHANT_ID", "test-merchant")
        object.__setattr__(self, "CLOVER_BASE_URL", "https://apisandbox.dev.clover.com")
        object.__setattr__(self, "ORDER_ID_HASH_SALT", "test-salt")
        object.__setattr__(self, "FLASK_SECRET_KEY", "test-secret")
        object.__setattr__(self, "DB_PATH", ":memory:")
        object.__setattr__(self, "MARGIN_ALERT_THRESHOLD", 0.10)
        object.__setattr__(self, "SECRET_KEY", "test-secret")
