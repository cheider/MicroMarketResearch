"""Template rendering with optional demo anonymization."""

from __future__ import annotations

from flask import g, render_template

from app.demo_anonymize import scrub_payload, scrub_template_context


def demo_mode_active() -> bool:
    return bool(getattr(g, "demo_anonymize", False))


def render_app_template(template_name: str, **context):
    if demo_mode_active():
        context = scrub_template_context(context)
    return render_template(template_name, **context)


def scrub_if_demo(data):
    if not demo_mode_active():
        return data
    if isinstance(data, dict):
        return scrub_template_context(data)
    if isinstance(data, list):
        return scrub_payload(data)
    return data
