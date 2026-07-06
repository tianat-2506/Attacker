from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_invoice(invoice: dict[str, Any]) -> str:
    ignored = {"invoice_hash", "funding_status", "confirmed_by"}
    payload = {key: value for key, value in invoice.items() if key not in ignored}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def invoice_hash(invoice: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_invoice(invoice).encode("utf-8")).hexdigest()


def double_financing_alert(invoice: dict[str, Any], existing_invoices: list[dict[str, Any]]) -> bool:
    current_hash = invoice_hash(invoice)
    for existing in existing_invoices:
        existing_hash = existing.get("invoice_hash")
        if not existing_hash or existing_hash == "generated-by-domain-module":
            existing_hash = invoice_hash(existing)
        if existing_hash == current_hash and existing.get("funding_status") == "funded":
            return True
    return False
