from app.engine.detect import detect_issues
from app.engine.worksheet import build_worksheet_csv


def test_worksheet_header_and_row_count(catalog_text: str) -> None:
    scan = detect_issues(catalog_text)
    csv = build_worksheet_csv(scan)
    lines = csv.split("\n")

    assert lines[0] == "issue_id,work,field,current_value,suggested,decision,publisher_value,note"
    assert len(lines) == 1 + len(scan.issues)


def test_worksheet_first_data_row_matches_first_issue(catalog_text: str) -> None:
    scan = detect_issues(catalog_text)
    csv = build_worksheet_csv(scan)
    lines = csv.split("\n")

    first = lines[1]
    assert first.startswith("HR-001,Skär,iswc,missing,external lookup match,,,")


def test_worksheet_em_dash_and_swedish_chars_preserved(catalog_text: str) -> None:
    scan = detect_issues(catalog_text)
    csv = build_worksheet_csv(scan)
    assert "Mikael Östberg — missing society" in csv
    assert "Drottningens Klang" in csv
