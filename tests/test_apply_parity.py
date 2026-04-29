from app.engine.apply import apply_decisions
from app.engine.csv_io import parse_csv

# Parity-port of apply-corrections.html. Spec §5 documents accept=5/edit=7,
# but counting decisions against the live JS gives accept=4/edit=8 — the spec
# itself says "the live JS is the source of truth" so we assert what the JS
# actually produces and flag the spec figure for reconciliation.


def _row_lookup(rows: list[list[str]], header: list[str], title: str) -> list[list[str]]:
    title_idx = [h.strip().lower() for h in header].index("title")
    return [r for r in rows if r[title_idx] == title]


def _col(header: list[str], name: str) -> int:
    return [h.strip().lower() for h in header].index(name)


def test_apply_totals(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    assert result.reject == 0
    assert result.accept == 4
    assert result.edit == 8
    assert len(result.log) == 12


def test_apply_iswc_mutations(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    iswc_idx = _col(header, "iswc")

    for row in _row_lookup(rows, header, "Skär"):
        assert row[iswc_idx] == "T-200.003.003-3"
    for row in _row_lookup(rows, header, "Drottningens Klang"):
        assert row[iswc_idx] == "T-200.004.004-4"
    for row in _row_lookup(rows, header, "Glömda Dagar"):
        assert row[iswc_idx] == "T-200.014.014-4"


def test_apply_split_mutations(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    name_idx = _col(header, "name")
    share_idx = _col(header, "share_percent")

    frusen = _row_lookup(rows, header, "Frusen Tid")
    shares = {row[name_idx]: row[share_idx] for row in frusen}
    assert shares["Maria Svensson"] == "60.0"
    assert shares["Johan Berg"] == "40.0"

    bergslagen = _row_lookup(rows, header, "Bergslagen")
    shares = {row[name_idx]: row[share_idx] for row in bergslagen}
    assert shares["Karin Lindgren"] == "40.0"
    assert shares["Anna Holm"] == "30.0"
    assert shares["Sofie Berg"] == "30.0"


def test_apply_ipi_mutations(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    name_idx = _col(header, "name")
    ipi_idx = _col(header, "ipi")

    vinterns = _row_lookup(rows, header, "Vinterns Ros")
    by_name = {row[name_idx]: row[ipi_idx] for row in vinterns}
    assert by_name["Lars Petersen"] == "00111222333"

    glomda = _row_lookup(rows, header, "Glömda Dagar")
    by_name = {row[name_idx]: row[ipi_idx] for row in glomda}
    assert by_name["Sofie Berg"] == "00777888999"


def test_apply_society_mutation(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    name_idx = _col(header, "name")
    soc_idx = _col(header, "society")

    nord = _row_lookup(rows, header, "Nordvinden")
    by_name = {row[name_idx]: row[soc_idx] for row in nord}
    assert by_name["Mikael Östberg"] == "STIM"


def test_apply_role_mutation_overzealous(catalog_text: str, filled_worksheet_text: str) -> None:
    # Per spec §4.2 quirk: accepting role fix overwrites every contributor of
    # the work, not just the bad one. Documented; will be fixed under
    # STRICT_ROLE_TARGETING flag in a follow-up.
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    role_idx = _col(header, "role")

    skuggornas = _row_lookup(rows, header, "Skuggornas Dans")
    assert all(row[role_idx] == "CA" for row in skuggornas)


def test_apply_writer_name_mutation(catalog_text: str, filled_worksheet_text: str) -> None:
    result = apply_decisions(catalog_text, filled_worksheet_text)
    rows = parse_csv(result.cleaned_csv)
    header = rows[0]
    name_idx = _col(header, "name")

    stjarn = _row_lookup(rows, header, "Stjärnvägen")
    names = {row[name_idx] for row in stjarn}
    assert "Lars Petersen" in names
    assert "L. Petersen" not in names


def test_apply_foreign_writer_logged_only(catalog_text: str, filled_worksheet_text: str) -> None:
    # Per spec §4.2: foreign_writer decision = accept produces no catalog
    # mutation; it is only logged. The new agreements table in v1 will close
    # this gap behind WRITE_AGREEMENTS_TABLE flag.
    result = apply_decisions(catalog_text, filled_worksheet_text)
    decisions = {(d.work, d.field): d for d in result.log}
    assert decisions[("Berlin Drömmar", "foreign_writer")].applied == "E declaration noted"
    assert decisions[("Paris i Höst", "foreign_writer")].applied == "E declaration noted"
