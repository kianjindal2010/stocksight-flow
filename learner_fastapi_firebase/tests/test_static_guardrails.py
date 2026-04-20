from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_legacy_db_or_django_auth_imports():
    banned = [
        "db.execute(",
        "django.contrib.auth",
        "from core.db import",
        "from core.models import",
        "subscription_required",
        "sqlite3",
        "sqlalchemy",
        "postgres",
        "psycopg",
        "cs50",
    ]
    for py_file in ROOT.rglob("*.py"):
        # Ignore tests to avoid matching the guardrail tokens declared in this file.
        if "tests" in py_file.parts:
            continue
        if ".venv" in py_file.parts or "site-packages" in py_file.parts:
            continue
        content = py_file.read_text(encoding="utf-8")
        for token in banned:
            assert token not in content, f"Found banned token '{token}' in {py_file}"


def test_no_pro_or_admin_navigation_in_layout():
    layout = (ROOT / "templates" / "layout.html").read_text(encoding="utf-8").lower()
    assert "admin panel" not in layout
    assert "team management" not in layout
    assert "coupon" not in layout
    assert "pricing" not in layout
