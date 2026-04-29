from app.services.email import render_after, render_analyzed, render_received


def test_render_analyzed_subject_and_body() -> None:
    e = render_analyzed(
        job_id="abc-123",
        health_report_url="https://x.example/r",
        worksheet_url="https://x.example/w",
    )
    assert e.subject == "HeyRoya – Kataloganalys klar"
    assert "abc-123" in e.body_html
    assert "https://x.example/r" in e.body_html
    assert "https://x.example/w" in e.body_html
    assert "fyll i korrigeringsfilen" in e.body_html


def test_render_received_subject_and_body() -> None:
    e = render_received(job_id="abc-123")
    assert e.subject == "HeyRoya – Korrigeringsfil mottagen"
    assert "Korrigeringsfil mottagen" in e.body_html
    assert "abc-123" in e.body_html


def test_render_after_subject_and_body() -> None:
    e = render_after(
        job_id="abc-123",
        after_report_url="https://x.example/after",
        corrected_catalog_url="https://x.example/cleaned",
    )
    assert e.subject == "HeyRoya – Efterrapport och korrigerad katalog klar"
    assert "abc-123" in e.body_html
    assert "https://x.example/after" in e.body_html
    assert "https://x.example/cleaned" in e.body_html


def test_render_analyzed_handles_missing_urls() -> None:
    e = render_analyzed(job_id="abc-123", health_report_url=None, worksheet_url=None)
    assert "länk saknas" in e.body_html
