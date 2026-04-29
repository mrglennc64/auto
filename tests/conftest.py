from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def catalog_text() -> str:
    return (FIXTURES / "test-15-mixed.csv").read_text(encoding="utf-8")


@pytest.fixture
def filled_worksheet_text() -> str:
    return (FIXTURES / "corrections-worksheet-test-15-filled.csv").read_text(
        encoding="utf-8"
    )
