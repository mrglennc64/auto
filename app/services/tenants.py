from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tenant
from app.models.db import session_scope


_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "whitelabel" / "pages"

_RAW_FILE_CACHE: dict[str, str] = {}
_RENDER_CACHE: dict[tuple[int, str], tuple[float, str]] = {}
_TENANT_CACHE: dict[str, tuple[float, Optional[dict]]] = {}

_RENDER_TTL_SECONDS = 60.0
_TENANT_TTL_SECONDS = 30.0

_PAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def templates_dir() -> Path:
    return _TEMPLATES_DIR


def normalize_host(host: str) -> str:
    return host.split(":", 1)[0].strip().lower()


def lookup_tenant_by_host(host: str) -> Optional[dict]:
    """Return a small dict snapshot of the tenant (or None). Cached for 30s."""
    h = normalize_host(host)
    now = time.time()
    cached = _TENANT_CACHE.get(h)
    if cached and (now - cached[0]) < _TENANT_TTL_SECONDS:
        return cached[1]

    snapshot: Optional[dict] = None
    with session_scope() as s:
        row = s.scalars(
            select(Tenant).where(
                Tenant.custom_domain == h,
                Tenant.status == "active",
            )
        ).one_or_none()
        if row is not None:
            snapshot = {
                "id": row.id,
                "slug": row.slug,
                "brand_name": row.brand_name,
                "contact_email": row.contact_email,
                "custom_domain": row.custom_domain,
                "primary_color": row.primary_color,
            }

    _TENANT_CACHE[h] = (now, snapshot)
    return snapshot


def resolve_page_filename(page: str) -> Optional[str]:
    """Map a URL path segment to a real filename in whitelabel/pages.

    "" or "/" -> "index.html"
    "portal" -> "portal.html"
    "portal.html" -> "portal.html"
    Anything that doesn't match a safe slug -> None.
    """
    name = page.strip("/").lower()
    if not name:
        name = "index"
    if name.endswith(".html"):
        name = name[:-5]
    if not _PAGE_NAME_RE.match(name):
        return None
    candidate = _TEMPLATES_DIR / f"{name}.html"
    if not candidate.is_file():
        return None
    return candidate.name


def _read_raw(filename: str) -> str:
    if filename not in _RAW_FILE_CACHE:
        path = _TEMPLATES_DIR / filename
        _RAW_FILE_CACHE[filename] = path.read_text(encoding="utf-8")
    return _RAW_FILE_CACHE[filename]


def _render_placeholders(html: str, tenant: dict) -> str:
    out = (
        html
        .replace("{{PartnerBrand}}", tenant["brand_name"])
        .replace("{{PartnerContact}}", tenant["contact_email"])
        .replace("{{PartnerDomain}}", tenant["custom_domain"])
    )
    # Color override: inject a <style> block right before </head> so it wins
    # over the page's own :root. Cheap, safe, no regex on the existing CSS.
    color = tenant["primary_color"]
    override = (
        "<style data-tenant-override>"
        f":root{{--accent:{color};--accent-soft:{color}1f;--accent-border:{color}66;}}"
        "</style>"
    )
    out = out.replace("</head>", f"{override}</head>", 1)
    return out


def render_page(tenant: dict, filename: str) -> str:
    key = (tenant["id"], filename)
    now = time.time()
    cached = _RENDER_CACHE.get(key)
    if cached and (now - cached[0]) < _RENDER_TTL_SECONDS:
        return cached[1]
    html = _render_placeholders(_read_raw(filename), tenant)
    _RENDER_CACHE[key] = (now, html)
    return html


def invalidate_caches() -> None:
    """Used by the admin CLI / tests after tenant edits."""
    _RAW_FILE_CACHE.clear()
    _RENDER_CACHE.clear()
    _TENANT_CACHE.clear()
