"""
UX demo presets — toggles nav and Insights sections without changing API/ETL.
"""

from dataclasses import dataclass

COOKIE_NAME = "mmr_ux_variant"

FULL_PERIOD_PRESETS = (
    ("week", "7d"),
    ("30d", "30d"),
    ("90d", "90d"),
    ("semester", "Semester"),
    ("lastweek", "Prior week"),
)

MAIN_PERIOD_PRESETS = (
    ("week", "This Week"),
    ("lastweek", "Last Week"),
)

INSIGHTS_PERIOD_PRESETS = (
    ("30d", "30 days"),
    ("90d", "90 days"),
    ("semester", "Semester"),
)


@dataclass(frozen=True)
class UxVariant:
    id: str
    label: str
    show_insights_nav: bool
    show_analysis_nav: bool
    dashboard_period_presets: tuple
    insights_period_presets: tuple
    insights_sections: frozenset


VARIANTS: dict[str, UxVariant] = {
    "team_main": UxVariant(
        id="team_main",
        label="Team baseline (main-style)",
        show_insights_nav=False,
        show_analysis_nav=False,
        dashboard_period_presets=MAIN_PERIOD_PRESETS,
        insights_period_presets=INSIGHTS_PERIOD_PRESETS,
        insights_sections=frozenset(),
    ),
    "dashboards_plus": UxVariant(
        id="dashboards_plus",
        label="Dashboard refresh",
        show_insights_nav=False,
        show_analysis_nav=True,
        dashboard_period_presets=FULL_PERIOD_PRESETS,
        insights_period_presets=INSIGHTS_PERIOD_PRESETS,
        insights_sections=frozenset(),
    ),
    "insights_core": UxVariant(
        id="insights_core",
        label="Insights (core)",
        show_insights_nav=True,
        show_analysis_nav=True,
        dashboard_period_presets=FULL_PERIOD_PRESETS,
        insights_period_presets=INSIGHTS_PERIOD_PRESETS,
        insights_sections=frozenset({"wow", "dow", "reorder"}),
    ),
    "insights_full": UxVariant(
        id="insights_full",
        label="Insights (full)",
        show_insights_nav=True,
        show_analysis_nav=True,
        dashboard_period_presets=FULL_PERIOD_PRESETS,
        insights_period_presets=INSIGHTS_PERIOD_PRESETS,
        insights_sections=frozenset({
            "wow", "dow", "reorder", "mix", "forecast",
            "stockout", "calendar", "active_events",
        }),
    ),
}

DEFAULT_VARIANT_ID = "insights_full"


def get_variant(variant_id: str) -> UxVariant:
    return VARIANTS.get(variant_id, VARIANTS[DEFAULT_VARIANT_ID])


def list_variants() -> list[UxVariant]:
    return list(VARIANTS.values())


def resolve_variant_id(
    query_value: str | None,
    cookie_value: str | None,
    env_default: str | None,
) -> str:
    if query_value and query_value in VARIANTS:
        return query_value
    if cookie_value and cookie_value in VARIANTS:
        return cookie_value
    if env_default and env_default in VARIANTS:
        return env_default
    return DEFAULT_VARIANT_ID
