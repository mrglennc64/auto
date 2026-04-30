"""Create a tenant row.

Usage:
    python scripts/add_tenant.py \
        --slug acme \
        --brand "Acme Catalog Services" \
        --email partner@acmecatalog.com \
        --domain portal.acmecatalog.com \
        --color "#1dd4b7"

Prints the generated API key on success.
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys

from sqlalchemy import select

from app.models import Tenant
from app.models.db import session_scope
from app.services.tenants import invalidate_caches


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create a whitelabel tenant.")
    p.add_argument("--slug", required=True, help="Short stable identifier (a-z0-9-).")
    p.add_argument("--brand", required=True, help="Display brand name.")
    p.add_argument("--email", required=True, help="Partner contact email.")
    p.add_argument("--domain", required=True, help="Custom domain (e.g. portal.acme.com).")
    p.add_argument("--color", default="#1dd4b7", help="Primary brand color, #rrggbb.")
    p.add_argument("--status", default="active", choices=["active", "suspended"], help="Initial status.")
    p.add_argument("--api-key", default=None, help="Optional pre-set API key (default: generated).")
    return p.parse_args(argv)


def validate(args: argparse.Namespace) -> None:
    slug = args.slug.lower()
    if not _SLUG_RE.match(slug):
        sys.exit(f"Invalid slug: {args.slug!r}")
    args.slug = slug

    domain = args.domain.lower()
    if not _DOMAIN_RE.match(domain):
        sys.exit(f"Invalid domain: {args.domain!r}")
    args.domain = domain

    if not _COLOR_RE.match(args.color):
        sys.exit(f"Invalid color: {args.color!r} (expected #rrggbb)")

    if "@" not in args.email or len(args.email) > 320:
        sys.exit(f"Invalid email: {args.email!r}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    validate(args)

    api_key = args.api_key or secrets.token_hex(32)

    with session_scope() as s:
        clash = s.scalars(
            select(Tenant).where(
                (Tenant.slug == args.slug) | (Tenant.custom_domain == args.domain)
            )
        ).first()
        if clash:
            print(
                f"ERROR: tenant already exists (slug={clash.slug}, domain={clash.custom_domain})",
                file=sys.stderr,
            )
            return 2

        t = Tenant(
            slug=args.slug,
            brand_name=args.brand,
            contact_email=args.email,
            custom_domain=args.domain,
            primary_color=args.color,
            status=args.status,
            api_key=api_key,
        )
        s.add(t)

    invalidate_caches()

    print(f"Created tenant: {args.slug}")
    print(f"  brand:         {args.brand}")
    print(f"  domain:        {args.domain}")
    print(f"  color:         {args.color}")
    print(f"  status:        {args.status}")
    print(f"  api_key:       {api_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
