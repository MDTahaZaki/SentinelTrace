"""Stage 2 - Normalise / Store.

Different sources format the same identifier differently: PGP fingerprints
with or without spaces, bech32 wallets in upper or lower case, mixed-case
handles. Normalising them first is what lets Stage 3 match identifiers exactly.
"""

import re
from datetime import date

_WHITESPACE = re.compile(r"\s+")


def norm_pgp(fp: str) -> str | None:
    """'4F2A 9C1E ...' and '4f2a9c1e...' -> '4F2A9C1E...'."""
    fp = _WHITESPACE.sub("", fp or "").upper()
    return fp or None


def norm_wallet(addr: str) -> str | None:
    """Bech32 (bc1...) addresses are case-insensitive, so store them lower-case."""
    addr = (addr or "").strip()
    if addr.lower().startswith("bc1"):
        addr = addr.lower()
    return addr or None


def norm_text(value: str) -> str | None:
    value = (value or "").strip()
    return value or None


def identifier_changes(raw_footprints: list[dict], store: list[dict]) -> list[dict]:
    """List identifiers whose formatting normalisation changed (shown in the UI log)."""
    changes = []
    for raw, clean in zip(raw_footprints, store):
        for field, label in (("pgp_fingerprint", "PGP key"), ("btc_wallet", "wallet")):
            before = (raw.get(field) or "").strip()
            after = clean[field] or ""
            if before and before != after:
                changes.append({"handle": clean["handle"], "field": label,
                                "before": before, "after": after})
    return changes


def normalise(raw_footprints: list[dict]) -> list[dict]:
    """Return clean footprint records ready for correlation."""
    store = []
    for fp in raw_footprints:
        store.append({
            "id": fp["id"],
            "handle": fp["handle"],
            "handle_key": fp["handle"].lower(),
            "source": fp["source"],
            "source_name": fp["source_name"],
            "pgp_fingerprint": norm_pgp(fp.get("pgp_fingerprint")),
            "btc_wallet": norm_wallet(fp.get("btc_wallet")),
            "ssl_cert_cn": norm_text(fp.get("ssl_cert_cn", "")),
            "server_banner": norm_text(fp.get("server_banner", "")),
            # Writing is kept verbatim: casing and punctuation are style signals.
            "writing_sample": fp.get("writing_sample", "").strip(),
            "last_seen": date.fromisoformat(fp["last_seen"]).isoformat(),
            "collected_at": fp["collected_at"],
        })
    return store
