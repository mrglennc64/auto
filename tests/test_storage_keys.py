from app.services.storage import build_key


def test_build_key_format() -> None:
    assert build_key("reports_after", "abc-123", "report.html") == "reports_after/abc-123/report.html"
    assert build_key("original_catalogs", "uuid", "catalog.csv") == "original_catalogs/uuid/catalog.csv"
