"""Relaydance — public /api/pricing endpoint (new-api fork standard).

new-api expresses prices as ratios vs a base of $2.00 per 1M tokens:
    input_per_1m  = model_ratio * 2.00
    output_per_1m = model_ratio * completion_ratio * 2.00

For per-call models (quota_type == 1), model_price is the absolute $/call.
"""

from __future__ import annotations

from ._common import FetchResult, PriceRecord, http_client

PROVIDER_ID = "relaydance"
PROVIDER_NAME = "Relaydance"
SOURCE_URL = "https://relaydance.com/api/pricing"
DISPLAY_URL = "https://relaydance.com/pricing"

# new-api convention: ratio=1 means $2 per 1M tokens.
NEW_API_BASE_USD_PER_1M = 2.0

QUOTA_TYPE_PER_TOKEN = 0
QUOTA_TYPE_PER_CALL = 1


def fetch() -> FetchResult:
    with http_client() as c:
        r = c.get(SOURCE_URL)
        r.raise_for_status()
        payload = r.json()

    if not payload.get("success", True):
        raise RuntimeError(f"relaydance API returned success=false: {payload}")

    models = payload.get("data", [])
    # group_ratio adjusts price per access group; we only price the "default" group.
    group_ratio = float((payload.get("group_ratio") or {}).get("default", 1))

    records: list[PriceRecord] = []
    for m in models:
        name = m.get("model_name")
        if not name:
            continue
        quota_type = m.get("quota_type", QUOTA_TYPE_PER_TOKEN)

        if quota_type == QUOTA_TYPE_PER_TOKEN:
            ratio = m.get("model_ratio")
            comp_ratio = m.get("completion_ratio")
            if ratio is None or float(ratio) <= 0:
                continue
            input_price = float(ratio) * NEW_API_BASE_USD_PER_1M * group_ratio
            records.append(_rec(name, "per_1m_input_tokens", input_price))
            if comp_ratio is not None and float(comp_ratio) > 0:
                output_price = (
                    float(ratio) * float(comp_ratio) * NEW_API_BASE_USD_PER_1M * group_ratio
                )
                records.append(_rec(name, "per_1m_output_tokens", output_price))
        elif quota_type == QUOTA_TYPE_PER_CALL:
            price = m.get("model_price")
            if price is None or float(price) <= 0:
                continue
            unit = _per_call_unit(m)
            records.append(_rec(name, unit, float(price) * group_ratio))

    return FetchResult(
        provider_id=PROVIDER_ID,
        records=records,
        raw_model_count=len(models),
    )


def _per_call_unit(m: dict) -> str:
    """Distinguish per-image vs per-second for per-call models based on the model name."""
    name = m.get("model_name", "").lower()
    if any(tag in name for tag in ("video", "i2v", "r2v", "t2v", "seedance", "video-edit")):
        return "per_second"
    if "image" in name or "imagine-image" in name:
        return "per_image"
    return "per_request"


def _rec(model_id: str, unit: str, price: float) -> PriceRecord:
    return PriceRecord(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        raw_model_name=model_id,
        channel_type="mixed",
        unit=unit,  # type: ignore[arg-type]
        price_usd=price,
        source_url=DISPLAY_URL,
        method="json-api",
    )
