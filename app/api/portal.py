from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.services.tenants import (
    lookup_tenant_by_host,
    render_page,
    resolve_page_filename,
)


router = APIRouter()


def _serve(host: str | None, page_path: str) -> HTMLResponse:
    if not host:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Host header missing")
    tenant = lookup_tenant_by_host(host)
    if tenant is None:
        # Not a configured tenant domain. Don't expose internals — just 404.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No portal configured for this host")
    filename = resolve_page_filename(page_path)
    if filename is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")
    html = render_page(tenant, filename)
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=60"})


@router.get("/portal/_health", include_in_schema=False)
def portal_health(host: str | None = Header(default=None)) -> JSONResponse:
    """Resolve the current Host to a tenant snapshot. Used for ops checks."""
    if not host:
        return JSONResponse({"host": None, "tenant": None})
    tenant = lookup_tenant_by_host(host)
    if tenant is None:
        return JSONResponse({"host": host, "tenant": None})
    return JSONResponse({"host": host, "tenant": {"slug": tenant["slug"], "brand_name": tenant["brand_name"]}})


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def portal_root(host: str | None = Header(default=None)) -> HTMLResponse:
    return _serve(host, "")


@router.get("/{page_path:path}", response_class=HTMLResponse, include_in_schema=False)
def portal_page(page_path: str, host: str | None = Header(default=None)) -> HTMLResponse:
    return _serve(host, page_path)
