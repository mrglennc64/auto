from app.engine.detect import detect_issues
from app.engine.score import classify_tone

EXPECTED_ISSUES = [
    ("HR-001", "Skär", "iswc", "missing", "external lookup match", "resolvable"),
    ("HR-002", "Drottningens Klang", "iswc", "missing", "external lookup match", "resolvable"),
    ("HR-003", "Frusen Tid", "split_total", "90.00%", "normalize to 100%", "blocking"),
    ("HR-004", "Bergslagen", "split_total", "110.00%", "normalize to 100%", "blocking"),
    ("HR-005", "Glömda Dagar", "iswc", "missing", "external lookup match", "resolvable"),
    ("HR-006", "Vinterns Ros", "writer_ipi", "Lars Petersen has no IPI", "publisher to provide", "blocking"),
    ("HR-007", "Nordvinden", "society", "Mikael Östberg — missing society", "publisher to confirm", "resolvable"),
    ("HR-008", "Berlin Drömmar", "foreign_writer", "Tobias Schmidt (GEMA) — no E/SE/AM declaration", "add E declaration", "blocking"),
    ("HR-009", "Paris i Höst", "foreign_writer", "Pierre Lambert (SACEM) — no E/SE/AM declaration", "add E declaration", "blocking"),
    ("HR-010", "Skuggornas Dans", "role", "WR (Anna Holm)", "change to CA (CWR-valid)", "blocking"),
    ("HR-011", "Stjärnvägen", "writer_name", "L. Petersen", "Lars Petersen (canonical)", "resolvable"),
    ("HR-012", "Glömda Dagar", "writer_ipi", "Sofie Berg has no IPI", "publisher to provide", "blocking"),
]


def test_detect_totals(catalog_text: str) -> None:
    scan = detect_issues(catalog_text)
    assert len(scan.titles) == 15
    assert scan.total_contribs == 31
    assert scan.blocking == 7
    assert scan.resolvable == 5
    assert scan.score == 53
    assert classify_tone(scan.score) == "warn"


def test_detect_issue_list(catalog_text: str) -> None:
    scan = detect_issues(catalog_text)
    assert len(scan.issues) == len(EXPECTED_ISSUES)
    for actual, expected in zip(scan.issues, EXPECTED_ISSUES):
        assert (
            actual.id,
            actual.work,
            actual.field,
            actual.current,
            actual.suggested,
            actual.severity,
        ) == expected
