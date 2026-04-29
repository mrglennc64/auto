import os
from base64 import b64encode

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("API_KEYS", "alpha,beta")
os.environ.setdefault("DASHBOARD_USER", "admin")
os.environ.setdefault("DASHBOARD_PASS", "changeme")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _basic(user: str, password: str) -> dict[str, str]:
    raw = f"{user}:{password}".encode()
    return {"Authorization": "Basic " + b64encode(raw).decode()}


def test_dashboard_requires_basic_auth() -> None:
    r = client.get("/dashboard")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_dashboard_rejects_wrong_creds() -> None:
    r = client.get("/dashboard", headers=_basic("admin", "wrong"))
    assert r.status_code == 401


def test_send_notification_requires_basic_auth() -> None:
    uuid_str = "00000000-0000-0000-0000-000000000001"
    r = client.post(f"/dashboard/notifications/{uuid_str}/send")
    assert r.status_code == 401
