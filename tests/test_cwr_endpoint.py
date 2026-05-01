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
    """Catalog with only title+name — triggers CwrValidationError (no IPI)."""
    return ("catalog.csv", b"title,name\nMidnight,Andersson\n", "text/csv")


def _valid_csv_file():
    """Complete catalog row with IPI + share — passes CWR validation."""
    body = (
        b"title,iswc,isrc,name,role,share_percent,ipi,society\n"
        b"Midnight Sun,T-123456789-0,SE6QZ2401001,ERIK ANDERSSON,CA,100,00712984310,STIM\n"
    )
    return ("catalog.csv", body, "text/csv")


def test_cwr_health_is_open() -> None:
    r = client.get("/api/cwr/health")
    assert r.status_code == 200
    body = r.json()
    assert body["implemented"] == "yes"


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


def test_cwr_generate_validation_error_when_writer_has_no_ipi() -> None:
    """Cleaned-CSV with title+name only triggers CwrValidationError → 422."""
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _csv_file()},
        data={
            "submitter_name": "Acme Publisher",
            "submitter_ipi": "00712984310",
            "target_pro": "STIM",
        },
        headers=HEADERS,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "cwr_validation_failed"
    assert "IPI" in body["message"]


def test_cwr_generate_rejects_csv_without_required_columns() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": ("c.csv", b"foo,bar\n1,2\n", "text/csv")},
        data={"submitter_name": "X", "submitter_ipi": "00712984310", "target_pro": "STIM"},
        headers=HEADERS,
    )
    assert r.status_code == 400
    assert "missing required columns" in r.json()["detail"]


def test_cwr_generate_returns_real_cwr_for_complete_catalog() -> None:
    r = client.post(
        "/api/cwr/generate",
        files={"cleaned_catalog_csv": _valid_csv_file()},
        data={
            "submitter_name": "Acme Publisher",
            "submitter_ipi": "00712984310",
            "target_pro": "STIM",
            "collection_scope": "LOCAL",
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert "cwr-package.v21" in r.headers.get("content-disposition", "")
    body = r.text
    # CWR v2.1 record types — every packet must have these
    assert body.startswith("HDR")
    assert "NWR" in body
    assert "SPU" in body
    assert "SWR" in body
    assert "PWR" in body
    assert "GRT" in body
    assert "TRL" in body
    # Sweden territory (752) for LOCAL scope + STIM pro
    assert "752" in body
    # Submitter name appears in HDR
    assert "ACME PUBLISHER" in body
