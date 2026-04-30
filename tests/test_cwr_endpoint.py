import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("API_KEYS", "alpha,beta")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.auth import verify_api_key  # noqa: E402

# Bypass auth in tests — these tests are about endpoint validation logic,
# not about whether the API key gate works (covered by test_api_auth.py).
# Without this override, tests fail when a real .env supplies different
# API keys at deploy time.
app.dependency_overrides[verify_api_key] = lambda: "test-key"

client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}


def _csv_file():
    return ("catalog.csv", b"title,name\nMidnight,Andersson\n", "text/csv")


def test_cwr_health_is_open() -> None:
    r = client.get("/api/cwr/health")
    assert r.status_code == 200
    body = r.json()
    assert body["implemented"] == "no"


def test_cwr_generate_rejects_unknown_target_pro() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={"submitter_name": "X", "submitter_ipi": "00712984310", "target_pro": "OTHER_PRO"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "target_pro" in r.json()["detail"]


def test_cwr_generate_rejects_non_digit_ipi() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={"submitter_name": "X", "submitter_ipi": "abcdefghijk", "target_pro": "ASCAP"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "submitter_ipi" in r.json()["detail"]


def test_cwr_generate_rejects_custom_scope_without_share() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={
            "submitter_name": "X",
            "submitter_ipi": "00712984310",
            "target_pro": "STIM",
            "collection_scope": "CUSTOM",
        },
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "custom_share_bp" in r.json()["detail"]


def test_cwr_generate_rejects_custom_scope_out_of_range() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={
            "submitter_name": "X",
            "submitter_ipi": "00712984310",
            "target_pro": "STIM",
            "collection_scope": "CUSTOM",
            "custom_share_bp": "20000",
        },
        headers=HEADERS,
    )
    assert r.status_code == 400


def test_cwr_generate_rejects_empty_catalog() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": ("catalog.csv", b"", "text/csv")},
        data={"submitter_name": "X", "submitter_ipi": "00712984310", "target_pro": "STIM"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "Empty" in r.json()["detail"]


def test_cwr_generate_returns_501_until_builder_wired() -> None:
    """When valid input arrives, the endpoint signals 'not yet implemented'
    rather than returning a fake CWR. Removes this once the real builder ships."""
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={
            "submitter_name": "Acme Publisher",
            "submitter_ipi": "00712984310",
            "target_pro": "ASCAP",
            "collection_scope": "WORLDWIDE",
        },
        headers=HEADERS,
    )
    assert r.status_code == 501
    body = r.json()
    assert body["error"] == "not_implemented"
    assert body["got"]["submitter_name"] == "Acme Publisher"
    assert body["got"]["target_pro"] == "ASCAP"
    assert body["got"]["catalog_bytes"] > 0
