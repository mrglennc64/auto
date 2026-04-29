from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import resend

from config.settings import settings

TemplateName = Literal["analyzed", "received", "after"]


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    body_html: str


def _link(url: str | None, label: str) -> str:
    if not url:
        return f'<span style="color:#888">{label} (länk saknas)</span>'
    return f'<a href="{url}" style="color:#0f6657;font-weight:600">{label}</a>'


def render_analyzed(job_id: str, health_report_url: str | None, worksheet_url: str | None) -> RenderedEmail:
    subject = "HeyRoya – Kataloganalys klar"
    body = f"""<!DOCTYPE html>
<html lang="sv"><body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#222;line-height:1.55;max-width:600px;padding:24px;">
<h2 style="color:#0f6657;font-size:18px;">HeyRoya – Kataloganalys klar</h2>
<p>Katalogjobb <code style="background:#f1f5f4;padding:2px 6px;border-radius:4px;">{job_id}</code> är klart.</p>
<ul style="padding-left:20px;">
  <li>Metadata Health Report (före): {_link(health_report_url, "hämta rapport")}</li>
  <li>Correction CSV (korrigeringsfil): {_link(worksheet_url, "hämta korrigeringsfil")}</li>
</ul>
<p><strong>Nästa steg:</strong> fyll i korrigeringsfilen och ladda upp den via portalen.</p>
<p style="color:#666;font-size:12px;border-top:1px solid #ddd;padding-top:12px;margin-top:24px;">
HeyRoya · Metadata compliance for Nordic music publishers
</p>
</body></html>"""
    return RenderedEmail(subject=subject, body_html=body)


def render_received(job_id: str) -> RenderedEmail:
    subject = "HeyRoya – Korrigeringsfil mottagen"
    body = f"""<!DOCTYPE html>
<html lang="sv"><body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#222;line-height:1.55;max-width:600px;padding:24px;">
<h2 style="color:#0f6657;font-size:18px;">HeyRoya – Korrigeringsfil mottagen</h2>
<p>Vi har mottagit korrigeringsfilen för jobb <code style="background:#f1f5f4;padding:2px 6px;border-radius:4px;">{job_id}</code>.</p>
<p>Systemet kör nu en ny analys med dina korrigeringar.</p>
<p>Du får ett nytt mail när &quot;efter&quot;-rapporten är klar.</p>
<p style="color:#666;font-size:12px;border-top:1px solid #ddd;padding-top:12px;margin-top:24px;">
HeyRoya · Metadata compliance for Nordic music publishers
</p>
</body></html>"""
    return RenderedEmail(subject=subject, body_html=body)


def render_after(job_id: str, after_report_url: str | None, corrected_catalog_url: str | None) -> RenderedEmail:
    subject = "HeyRoya – Efterrapport och korrigerad katalog klar"
    body = f"""<!DOCTYPE html>
<html lang="sv"><body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#222;line-height:1.55;max-width:600px;padding:24px;">
<h2 style="color:#0f6657;font-size:18px;">HeyRoya – Efterrapport och korrigerad katalog klar</h2>
<p>&quot;Efter&quot;-rapporten för jobb <code style="background:#f1f5f4;padding:2px 6px;border-radius:4px;">{job_id}</code> är klar.</p>
<p>Du kan ladda ner:</p>
<ul style="padding-left:20px;">
  <li>Metadata Health Report (efter): {_link(after_report_url, "hämta rapport")}</li>
  <li>Korrigerad katalog (CSV): {_link(corrected_catalog_url, "hämta korrigerad katalog")}</li>
</ul>
<p>Rapporten visar kvarvarande avvikelser och uppdaterad risknivå.</p>
<p style="color:#666;font-size:12px;border-top:1px solid #ddd;padding-top:12px;margin-top:24px;">
HeyRoya · Metadata compliance for Nordic music publishers
</p>
</body></html>"""
    return RenderedEmail(subject=subject, body_html=body)


def send_via_resend(recipient: str, subject: str, body_html: str) -> str:
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY not configured")
    resend.api_key = settings.resend_api_key
    params: dict = {
        "from": settings.resend_from,
        "to": [recipient],
        "subject": subject,
        "html": body_html,
    }
    if settings.resend_operator_bcc:
        params["bcc"] = [settings.resend_operator_bcc]
    response = resend.Emails.send(params)
    return response.get("id", "")
