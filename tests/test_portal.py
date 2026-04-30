import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("API_KEYS", "alpha,beta")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import tenants as tenants_svc  # noqa: E402

client = TestClient(app)


SAMPLE_TENANT = {
    "id": 1,
    "slug": "acme",
    "brand_name": "Acme Catalog Services",
    "contact_email": "partner@acmecatalog.com",
    "custom_domain": "portal.acmecatalog.com",
    "primary_color": "#ff6600",
}


def setup_function() -> None:
    tenants_svc.invalidate_caches()


# --- resolve_page_filename ---


def test_resolve_root_returns_index() -> None:
    assert tenants_svc.resolve_page_filename("") == "index.html"
    assert tenants_svc.resolve_page_filename("/") == "index.html"


def test_resolve_known_page_without_extension() -> None:
    assert tenants_svc.resolve_page_filename("portal") == "portal.html"
    assert tenants_svc.resolve_page_filename("how-it-works") == "how-it-works.html"


def test_resolve_known_page_with_extension() -> None:
    assert tenants_svc.resolve_page_filename("portal.html") == "portal.html"


def test_resolve_unknown_page_returns_none() -> None:
    assert tenants_svc.resolve_page_filename("does-not-exist") is None


def test_resolve_path_traversal_attempt_returns_none() -> None:
    # Anything with slashes, dots, or unsafe chars should be rejected
    assert tenants_svc.resolve_page_filename("../etc/passwd") is None
    assert tenants_svc.resolve_page_filename("foo/bar") is None
    assert tenants_svc.resolve_page_filename(".env") is None


# --- normalize_host ---


def test_normalize_host_strips_port_and_lowercases() -> None:
    assert tenants_svc.normalize_host("Portal.Acme.com:8000") == "portal.acme.com"


# --- placeholder rendering ---


def test_render_replaces_brand_contact_domain() -> None:
    html = "<title>{{PartnerBrand}}</title><a href='mailto:{{PartnerContact}}'>x</a><p>{{PartnerDomain}}</p>"
    out = tenants_svc._render_placeholders(html + "</head>", SAMPLE_TENANT)
    assert "Acme Catalog Services" in out
    assert "partner@acmecatalog.com" in out
    assert "portal.acmecatalog.com" in out
    assert "{{PartnerBrand}}" not in out


def test_render_injects_color_override_before_head_close() -> None:
    html = "<head><style>:root{--accent:#1dd4b7;}</style></head><body></body>"
    out = tenants_svc._render_placeholders(html, SAMPLE_TENANT)
    assert "--accent:#ff6600" in out
    assert "data-tenant-override" in out
    # Override appears before </head> so it wins the cascade
    assert out.index("data-tenant-override") < out.index("</head>")


# --- route behavior ---


def test_portal_root_returns_404_when_host_unknown(monkeypatch) -> None:
    monkeypatch.setattr(tenants_svc, "lookup_tenant_by_host", lambda h: None)
    r = client.get("/", headers={"Host": "unknown.example.com"})
    assert r.status_code == 404


def test_portal_health_returns_null_tenant_for_unknown_host(monkeypatch) -> None:
    monkeypatch.setattr(tenants_svc, "lookup_tenant_by_host", lambda h: None)
    r = client.get("/portal/_health", headers={"Host": "unknown.example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "unknown.example.com"
    assert body["tenant"] is None


def test_portal_serves_index_when_host_matches_tenant(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.portal.lookup_tenant_by_host", lambda h: SAMPLE_TENANT
    )
    r = client.get("/", headers={"Host": "portal.acmecatalog.com"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "Acme Catalog Services" in body
    assert "{{PartnerBrand}}" not in body
    assert "--accent:#ff6600" in body


def test_portal_serves_portal_page_when_path_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.portal.lookup_tenant_by_host", lambda h: SAMPLE_TENANT
    )
    r = client.get("/portal", headers={"Host": "portal.acmecatalog.com"})
    assert r.status_code == 200
    assert "Acme Catalog Services" in r.text
    # Portal page links to the local Part 1 + Part 2 partner-safe tools
    assert 'href="scan-catalog.html"' in r.text
    assert 'href="apply-corrections.html"' in r.text


def test_portal_returns_404_for_unknown_page_under_known_tenant(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.portal.lookup_tenant_by_host", lambda h: SAMPLE_TENANT
    )
    r = client.get("/no-such-page", headers={"Host": "portal.acmecatalog.com"})
    assert r.status_code == 404


def test_existing_api_routes_still_work_on_other_hosts() -> None:
    # /api/health is open and host-agnostic — must keep working regardless of Host
    r = client.get("/api/health", headers={"Host": "automation.heyroya.se"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    r = client.get("/api/health", headers={"Host": "portal.acmecatalog.com"})
    assert r.status_code == 200
