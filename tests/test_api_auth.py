import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("API_KEYS", "alpha,beta")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_is_open() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status_route_requires_api_key() -> None:
    uuid_str = "00000000-0000-0000-0000-000000000001"
    r = client.get(f"/api/jobs/{uuid_str}/status")
    assert r.status_code == 401


def test_status_route_rejects_wrong_key() -> None:
    uuid_str = "00000000-0000-0000-0000-000000000001"
    r = client.get(
        f"/api/jobs/{uuid_str}/status",
        headers={"X-API-Key": "not-a-real-key"},
    )
    assert r.status_code == 401


def test_results_route_requires_api_key() -> None:
    uuid_str = "00000000-0000-0000-0000-000000000001"
    r = client.get(f"/api/jobs/{uuid_str}/results")
    assert r.status_code == 401


def test_after_route_requires_api_key() -> None:
    uuid_str = "00000000-0000-0000-0000-000000000001"
    r = client.get(f"/api/jobs/{uuid_str}/after")
    assert r.status_code == 401


def test_upload_catalog_requires_api_key() -> None:
    r = client.post(
        "/api/upload/catalog",
        files={"file": ("c.csv", b"title,name\na,b\n", "text/csv")},
        data={"publisher_id": "demo"},
    )
    assert r.status_code == 401


def test_upload_corrections_requires_api_key() -> None:
    r = client.post(
        "/api/upload/corrections",
        files={"file": ("c.csv", b"x,y\n1,2\n", "text/csv")},
        data={"job_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 401
