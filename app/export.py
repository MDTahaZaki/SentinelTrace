"""CSV / JSON export of the current (filtered) result set."""

import csv
import io
import json
from datetime import datetime, timezone

CSV_COLUMNS = ["actor", "suggested_actor", "handle", "source", "pgp_fingerprint", "btc_wallet",
               "ssl_cert_cn", "confidence", "top_link", "last_seen"]


def to_csv(profiles: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for p in profiles:
        top = p["top_link"]
        writer.writerow({
            **{k: p.get(k) or "" for k in CSV_COLUMNS},
            "confidence": p["confidence"] if p["confidence"] is not None else "",
            "top_link": f"{top['handle']} ({top['confidence']}): {top['reason']}" if top else "",
        })
    return buf.getvalue()


def to_json(profiles: list[dict], query: dict) -> str:
    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notice": "SentinelTrace demo export - synthetic data only",
        "query": query,
        "count": len(profiles),
        "profiles": profiles,
    }, indent=2, ensure_ascii=False)
