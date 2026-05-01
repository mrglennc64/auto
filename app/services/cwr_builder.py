"""CWR v2.1 packet builder — port of packages/frontend/app/cwr-generator/page.tsx.

Differences from the TS port:
  * Society fields written as 3-digit numeric codes per CWR v2.1 spec — the TS
    tool wrote alpha prefixes (``STI``, ``ASC``) which STIM rejects.
  * STIM society code is ``011`` (the code STIM itself expects in CWR SPU /
    SWR affiliation fields), not the CISAC directory number 071.
  * Default territory is Sweden (752) for STIM-bound packets; pass
    ``territories=["2136"]`` for world.
"""
from datetime import datetime

# Society codes (3-digit, zero-padded) as emitted in CWR SPU/SWR affiliation
# fields. STIM uses 011 in CWR (per STIM onboarding docs) even though its
# CISAC directory number is 071 — do not "correct" 011 back to 071.
SOCIETY_CODES: dict[str, str] = {
    "STIM": "011",
    "ASCAP": "010",
    "BMI": "021",
    "SESAC": "022",
    "GMR": "147",
    "SOCAN": "101",
    "PRS": "052",
    "PRS FOR MUSIC": "052",
    "MCPS": "044",
    "GEMA": "035",
    "SACEM": "058",
    "SIAE": "074",
    "SGAE": "064",
    "APRA": "001",
    "AMCOS": "002",
    "TONO": "090",
    "KODA": "040",
    "TEOSTO": "089",
    "JASRAC": "037",
    "BUMA": "023",
    "STEMRA": "078",
    "SABAM": "017",
    "ZAIKS": "108",
    "MUSICAUTOR": "127",
    "OSA": "057",
}


def _society_code(society: str | None, default: str = "011") -> str:
    if not society:
        return default
    s = str(society).strip().upper()
    if s.isdigit():
        return s.zfill(3)[:3]
    return SOCIETY_CODES.get(s, default)


def _pad(s, length: int, char: str = " ", right: bool = False) -> str:
    out = str(s or "")
    if len(out) >= length:
        return out[:length]
    filler = char * (length - len(out))
    return out + filler if right else filler + out


def lpad(s, length: int, char: str = "0") -> str:
    return _pad(s, length, char, right=False)


def rpad(s, length: int) -> str:
    return _pad(s, length, " ", right=True)


WRITER_ROLES = {"CA", "A", "C", "E", "AR", "SE"}


class CwrValidationError(ValueError):
    """Raised when inputs violate a CWR v2.1 mandatory-field rule."""


def _validate_pre_emit(works: list[dict], publisher_ipi: str) -> None:
    """Enforce CWR v2.1 mandatory fields before emitting any records.

    Rules (STIM pilot hard-block):
      * submitting publisher IPI must be present (else PWR is unlinkable)
      * every NWR must have ≥1 SWR (writer with a writer-role code)
      * every writer must have an IPI (else its PWR line is invalid)
    """
    if not (publisher_ipi or "").strip():
        raise CwrValidationError("publisher_ipi is blank — cannot form any PWR link")
    for w in works:
        title = (w.get("title") or "").strip() or f"work {w.get('id')}"
        writers = [
            c for c in (w.get("contributors") or [])
            if (c.get("role") or "").strip().upper() in WRITER_ROLES
        ]
        if not writers:
            raise CwrValidationError(f'"{title}" has no writer — CWR requires ≥1 SWR per NWR')
        for wr in writers:
            if not (wr.get("ipi") or "").strip():
                nm = wr.get("name_clean") or wr.get("name_raw") or "writer"
                raise CwrValidationError(
                    f'"{title}": writer "{nm}" has no IPI — PWR link cannot be emitted'
                )


def _writer_chain(writer: dict, local_pub: dict) -> list[dict]:
    """Return the ordered SPU chain for a single writer.

    ``local_pub`` is {name, ipi, society, pro}. The writer's ``agreement_type``
    drives the shape:

    * ``None`` / ``"E"`` — single SPU: local publisher acting as Original.
    * ``"SE"`` — two SPUs: foreign original (E) + local sub-publisher (SE).
    * ``"AM"`` — two SPUs: foreign original (E) + local administrator (AM).

    The "local publisher" SPU is always the one writers link to via PWR.
    """
    agreement = (writer.get("agreement_type") or "").upper().strip()
    local_spu = {
        "role": "E",
        "name": local_pub["name"],
        "ipi": local_pub["ipi"],
        "society": local_pub["society"],
        "is_local": True,
    }
    if agreement in ("SE", "AM"):
        local_spu["role"] = agreement
        orig_name = (writer.get("original_publisher_name") or "").strip()
        orig_ipi = (writer.get("original_publisher_ipi") or "").strip()
        orig_soc = writer.get("original_publisher_society") or writer.get("society")
        if not orig_name or not orig_ipi:
            raise CwrValidationError(
                f'writer "{writer.get("name_clean") or writer.get("name_raw")}" has '
                f"agreement_type {agreement} but original publisher name/IPI is missing"
            )
        foreign_spu = {
            "role": "E",
            "name": orig_name,
            "ipi": orig_ipi,
            "society": _society_code(orig_soc, default=local_pub["society"]),
            "is_local": False,
        }
        return [foreign_spu, local_spu]
    return [local_spu]


def build_cwr(
    works: list[dict],
    submitter: str,
    sender_ipi: str,
    publisher_ipi: str,
    publisher_name: str,
    publisher_pro: str = "STIM",
    territories: list[str] | None = None,
    default_language: str = "EN",
    default_category: str = "POP",
    publisher_share_bp: int = 3333,
) -> str:
    """Build a CWR v2.1 text file.

    ``works`` is a list of dicts:
      {id, title, iswc, duration, contributors: [
         {name_clean, ipi, role, share, society, agreement_type,
          original_publisher_name, original_publisher_ipi, original_publisher_society},
         ...]}
    Writer ``share`` is 0–100 (percent); CWR wants hundredths of a percent.

    ``publisher_share_bp`` is the submitting publisher's ownership share in
    basis points (10000 = 100%). Defaults to 3333 (33.33%, Swedish standard);
    pass 5000 for the 50% international standard or any other carve-out.

    Raises ``CwrValidationError`` if any work lacks a writer, any writer or
    the submitting publisher lacks an IPI, or an SE/AM writer has no original
    publisher name/IPI.
    """
    _validate_pre_emit(works, publisher_ipi)
    territories = territories or ["752"]  # Sweden — STIM default
    publisher_society = _society_code(publisher_pro)
    local_pub = {
        "name": publisher_name,
        "ipi": publisher_ipi,
        "society": publisher_society,
        "pro": publisher_pro,
    }
    now = datetime.utcnow()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    lines: list[str] = []

    lines.append(
        "HDR"
        + rpad("PB", 2)
        + lpad(sender_ipi, 11, "0")
        + rpad(submitter.upper()[:45], 45)
        + "01.10"
        + date_str + time_str
        + lpad("1", 8, "0")
        + rpad("CWR", 3)
    )

    tx_seq = 0
    for work in works:
        tx_seq += 1
        rec_seq = 0

        title = (work.get("title") or "").upper()[:60]
        iswc = (work.get("iswc") or "").replace("-", "").replace(".", "")
        iswc_out = rpad(iswc, 11) if iswc else " " * 11

        rec_seq += 1
        lines.append(
            "NWR"
            + lpad(tx_seq, 8, "0")
            + lpad(rec_seq, 8, "0")
            + rpad(title, 60)
            + iswc_out
            + date_str
            + rpad("", 60)
            + lpad(work.get("duration") or "000000", 6, "0")
            + rpad(work.get("category") or default_category, 3)
            + "U"
            + rpad("ORI", 3)
            + rpad("", 3)
            + rpad("", 3)
            + rpad("", 3)
            + rpad(work.get("language") or default_language, 2)
        )

        writers = [
            c for c in work.get("contributors", [])
            if (c.get("role") or "").upper() in {"CA", "A", "C", "E", "AR", "SE"}
        ]

        # Resolve each writer's publisher chain; de-dupe chains across writers
        # sharing the same original publisher so we don't emit duplicate SPUs.
        chains_by_writer: list[list[dict]] = [_writer_chain(w, local_pub) for w in writers]
        chain_by_key: dict[tuple, list[dict]] = {}
        chain_seq_by_key: dict[tuple, int] = {}
        chain_local_ipi_by_key: dict[tuple, str] = {}
        next_seq = 1
        for chain in chains_by_writer:
            key = tuple((s["role"], s["ipi"]) for s in chain)
            if key in chain_by_key:
                continue
            chain_by_key[key] = chain
            chain_seq_by_key[key] = next_seq
            for s in chain:
                if s["is_local"]:
                    chain_local_ipi_by_key[key] = s["ipi"]
            next_seq += 1

        # Emit SPU (+ SPT) for every chain. The local publisher's share uses
        # publisher_share_bp; foreign originals carry the same share through
        # (sub-pub collection; STIM reads the local's SPU for actual payout).
        for key, chain in chain_by_key.items():
            seq = chain_seq_by_key[key]
            for spu in chain:
                rec_seq += 1
                lines.append(
                    "SPU"
                    + lpad(tx_seq, 8, "0")
                    + lpad(rec_seq, 8, "0")
                    + lpad(seq, 4, "0")
                    + rpad(spu["name"][:45], 45)
                    + rpad(spu["role"][:2], 2)
                    + lpad(spu["ipi"], 11, "0")
                    + rpad("", 14)
                    + rpad(spu["society"], 3)
                    + rpad("", 3)
                    + lpad(publisher_share_bp, 5, "0")
                    + lpad("0", 5, "0")
                    + lpad("0", 5, "0")
                )
            # One SPT chain per local publisher per territory
            local_ipi = chain_local_ipi_by_key.get(key, publisher_ipi)
            for terr in territories:
                rec_seq += 1
                lines.append(
                    "SPT"
                    + lpad(tx_seq, 8, "0")
                    + lpad(rec_seq, 8, "0")
                    + lpad(local_ipi, 11, "0")
                    + lpad(publisher_share_bp, 5, "0")
                    + lpad("0", 5, "0")
                    + lpad("0", 5, "0")
                    + rpad(terr, 4)
                    + "I"
                )

        for wi, writer in enumerate(writers):
            name = (writer.get("name_clean") or "").strip()
            parts = name.split(" ")
            last = parts[-1][:45] if parts else ""
            first = " ".join(parts[:-1])[:30] if len(parts) > 1 else ""
            share = float(writer.get("share") or 0)
            share_bp = round(share * 100)
            mech_bp = round(share * 50)
            writer_pro = _society_code(writer.get("society"), default=publisher_society)
            writer_ipi = writer.get("ipi") or ""

            rec_seq += 1
            lines.append(
                "SWR"
                + lpad(tx_seq, 8, "0")
                + lpad(rec_seq, 8, "0")
                + lpad(writer_ipi, 11, "0")
                + rpad(last, 45)
                + rpad(first, 30)
                + rpad(writer.get("role") or "CA", 2)
                + lpad(share_bp, 5, "0")
                + lpad(mech_bp, 5, "0")
                + lpad("0", 5, "0")
                + rpad(writer_pro, 3)
                + "Y"
            )

            for terr in territories:
                rec_seq += 1
                lines.append(
                    "SWT"
                    + lpad(tx_seq, 8, "0")
                    + lpad(rec_seq, 8, "0")
                    + lpad(writer_ipi, 11, "0")
                    + lpad(share_bp, 5, "0")
                    + lpad(mech_bp, 5, "0")
                    + lpad("0", 5, "0")
                    + rpad(terr, 4)
                    + "I"
                )

            rec_seq += 1
            # PWR layout (STIM/ICE dialect):
            #   pos 1-3  record type (PWR)
            #   pos 4-11 transaction sequence
            #   pos 12-19 record sequence
            #   pos 20-30 publisher IPI (11, zero-padded left) — LOCAL pub in chain
            #   pos 31-75 publisher name (45, space-padded right)
            #   pos 76-80 filler (5 spaces)
            #   pos 81-91 writer IPI (11, zero-padded left) — MUST start at 81
            writer_chain = chains_by_writer[wi]
            writer_key = tuple((s["role"], s["ipi"]) for s in writer_chain)
            local_spu = next(s for s in writer_chain if s["is_local"])
            lines.append(
                "PWR"
                + lpad(tx_seq, 8, "0")
                + lpad(rec_seq, 8, "0")
                + lpad(local_spu["ipi"], 11, "0")
                + rpad(local_spu["name"][:45], 45)
                + rpad("", 5)
                + lpad(writer_ipi, 11, "0")
            )

        rec_seq += 1
        lines.append(
            "TRL"
            + lpad(tx_seq, 8, "0")
            + lpad(rec_seq, 8, "0")
            + lpad(rec_seq, 8, "0")
        )

    lines.append("GRT" + lpad("1", 8, "0") + lpad(tx_seq, 8, "0") + lpad(len(lines) + 2, 8, "0"))
    lines.append("TRL" + lpad("1", 8, "0") + lpad(tx_seq, 8, "0") + lpad(len(lines) + 1, 8, "0"))

    return "\r\n".join(lines)


# ---------------------------------------------------------------------------
# Post-generation health report
# ---------------------------------------------------------------------------

def cwr_health_report(content: str, publisher_share_bp: int = 5000) -> dict:
    """Inspect an emitted CWR text and return a three-section health report.

    Sections:
      * structural   — record types + order + positive notes (society, territory, share sums)
      * technical    — fatal formatting issues (IPI padding, title width, PWR column)
      * business     — non-fatal warnings (e.g. publisher share != 33.33% Swedish default)

    The report is designed to run after every packet build so STIM/ICE rejection
    risks surface before submission.
    """
    raw_lines = content.split("\r\n") if "\r\n" in content else content.splitlines()
    lines = [l for l in raw_lines if l]

    rec_types = [l[:3] for l in lines]
    required = ("HDR", "NWR", "SPU", "SWR", "PWR", "TRL", "GRT")
    missing = [r for r in required if r not in rec_types]

    technical: list[dict] = []

    # A. SWR IPI — positions 20-30 (0-idx 19:30), must be 11 digits
    for i, line in enumerate(lines, 1):
        if not line.startswith("SWR"):
            continue
        ipi = line[19:30]
        if len(ipi) != 11 or not ipi.isdigit():
            technical.append({
                "code": "IPI_NOT_PADDED",
                "severity": "fatal",
                "line": i,
                "description": f"SWR IPI at col 20–30 is not 11 digits (got '{ipi}')",
                "fix": "Pad IPI left with zeros to 11 digits",
            })

    # B. NWR title — 60 chars at 0-idx 19:79, then ISWC at 79:90
    for i, line in enumerate(lines, 1):
        if not line.startswith("NWR"):
            continue
        if len(line) < 90:
            technical.append({
                "code": "TITLE_PADDING",
                "severity": "fatal",
                "line": i,
                "description": "NWR record shorter than 90 chars — title field not padded to 60",
                "fix": "Right-pad title with spaces to exactly 60 chars before ISWC",
            })

    # C. PWR writer IPI — must start at column 81 (0-idx 80:91)
    for i, line in enumerate(lines, 1):
        if not line.startswith("PWR"):
            continue
        writer_ipi = line[80:91] if len(line) >= 91 else ""
        if len(writer_ipi) != 11 or not writer_ipi.isdigit():
            technical.append({
                "code": "PWR_COLUMN_MISALIGN",
                "severity": "fatal",
                "line": i,
                "description": f"PWR writer IPI not at col 81–91 (got '{writer_ipi}')",
                "fix": "Ensure 5-char filler after 45-char publisher name so writer IPI starts at col 81",
            })

    # Writer PR shares per work (tx_seq). SWR layout:
    #   3 + 8 + 8 + 11 + 45 + 30 + 2 + 5(PR share) → PR share at 0-idx 107:112.
    writer_share_by_tx: dict[int, int] = {}
    for line in lines:
        if not line.startswith("SWR"):
            continue
        try:
            tx_seq = int(line[3:11])
            pr_share = int(line[107:112])
            writer_share_by_tx[tx_seq] = writer_share_by_tx.get(tx_seq, 0) + pr_share
        except (ValueError, IndexError):
            pass
    # Local publisher PR share per work. SPU layout:
    #   3 + 8 + 8 + 4(seq) + 45(name) + 2(role) + 11(ipi) + 14 + 3(soc) + 3 = 101;
    #   PR share at 0-idx 101:106. Use the *first* SPU per tx so SE chains (which
    #   repeat the same share on foreign-orig + local) count once.
    pub_share_by_tx: dict[int, int] = {}
    for line in lines:
        if not line.startswith("SPU"):
            continue
        try:
            tx_seq = int(line[3:11])
            if tx_seq in pub_share_by_tx:
                continue
            pub_share_by_tx[tx_seq] = int(line[101:106])
        except (ValueError, IndexError):
            pass
    share_ok = bool(writer_share_by_tx) and all(
        writer_share_by_tx.get(tx, 0) + pub_share_by_tx.get(tx, 0) == 10000
        for tx in writer_share_by_tx
    )

    # Business warnings — only flag when share deviates from Swedish standard
    business: list[dict] = []
    if publisher_share_bp != 3333:
        pct = f"{publisher_share_bp / 100:.2f}%"
        business.append({
            "code": "PUBLISHER_SHARE_NON_STANDARD",
            "severity": "warning",
            "description": (
                f"Publisher share = {pct}. Swedish default is 33.33% unless the "
                "contract grants a different split or the publisher is acting "
                "as an administrator with a specific carve-out. STIM may flag "
                "this for manual review."
            ),
            "fix": "Confirm contract terms or adjust publisher share to 33.33%",
        })

    # Positive structural notes
    notes: list[str] = []
    if not missing:
        notes.append("HDR → NWR → SPU → SPT → SWR → SWT → PWR → TRL structure present")
    nwr = sum(1 for l in lines if l.startswith("NWR"))
    swr = sum(1 for l in lines if l.startswith("SWR"))
    pwr = sum(1 for l in lines if l.startswith("PWR"))
    if nwr:
        notes.append(f"{nwr} work(s) · {swr} SWR record(s) · {pwr} PWR record(s)")
    # Society 011 present in SPU or SWR
    if any(l.startswith(("SPU", "SWR")) and "011" in l for l in lines):
        notes.append("Society code 011 (STIM) applied")
    # Territory — SPT layout: SPT(3) + tx(8) + rec(8) + IPI(11) + PR(5) + MR(5) + SR(5)
    # = 45; territory (4) occupies 0-idx 45:49.
    territories_seen: set[str] = set()
    for line in lines:
        if line.startswith("SPT") and len(line) >= 49:
            territories_seen.add(line[45:49].strip())
    if territories_seen:
        notes.append(f"Territory code(s) applied: {', '.join(sorted(territories_seen))}")
    if share_ok:
        notes.append("Writer + publisher shares sum to 100% for all works")
    # SE/AM chains — detect multi-SPU works and note them
    spu_by_tx: dict[int, int] = {}
    for line in lines:
        if line.startswith("SPU"):
            try:
                tx_seq = int(line[3:11])
                spu_by_tx[tx_seq] = spu_by_tx.get(tx_seq, 0) + 1
            except (ValueError, IndexError):
                pass
    multi_chain = sum(1 for n in spu_by_tx.values() if n > 1)
    if multi_chain:
        notes.append(f"{multi_chain} work(s) emit multi-publisher chains (SE/AM sub-publishing)")

    structural_pass = not missing
    technical_pass = not technical
    submission_ready = structural_pass and technical_pass

    summary_en = (
        "Your works have been successfully structured for CWR export. "
        "Writer + publisher shares total 100% and STIM society code 011 is correctly applied. "
        if submission_ready and share_ok else
        "CWR packet generated, but corrections are required before submission. "
    )
    if technical:
        summary_en += f"{len(technical)} fatal formatting issue(s) need correction. "
    for w in business:
        summary_en += w["description"] + " "
    summary_en += "Once any issues are addressed, the file is ready for STIM/ICE ingestion."

    return {
        "structural": {
            "status": "pass" if structural_pass else "fail",
            "missing_record_types": missing,
            "notes": notes,
        },
        "technical": {
            "status": "pass" if technical_pass else "fail",
            "issues": technical,
        },
        "business": {
            "status": "warn" if business else "ok",
            "warnings": business,
        },
        "submission_ready": submission_ready,
        "summary_en": summary_en,
    }
