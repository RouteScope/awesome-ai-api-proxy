"""Atlas Cloud — public api.atlascloud.ai/v1/models JSON (OpenAI-compatible shape).

Exposes prompt/completion/image/request prices as $/token in the `pricing` block.
"""

from __future__ import annotations

from ._common import FetchResult, PriceRecord, http_client, per_token_to_per_1m

PROVIDER_ID = "atlascloud"
PROVIDER_NAME = "Atlas Cloud"
SOURCE_URL = "https://api.atlascloud.ai/v1/models"
DISPLAY_URL = "https://www.atlascloud.ai/models"


def fetch() -> FetchResult:
    with http_client() as c:
        r = c.get(SOURCE_URL)
        r.raise_for_status()
        payload = r.json()

    models = payload.get("data", [])
    records: list[PriceRecord] = []
    for m in models:
        model_id = m.get("id")
        if not model_id:
            continue
        pricing = m.get("pricing")
        # 13/118 models use tiered pricing (a list of brackets keyed on min_context).
        # Take the base (cheapest / no-threshold) bracket — that's what shows on the marketing page.
        if isinstance(pricing, list):
            bracket = _pick_base_bracket(pricing)
        elif isinstance(pricing, dict):
            bracket = pricing
        else:
            continue

        for unit, value, scale_per_1m in _extract_units(bracket):
            records.append(
                _rec(
                    model_id,
                    unit,
                    per_token_to_per_1m(value) if scale_per_1m else float(value),
                )
            )

    return FetchResult(
        provider_id=PROVIDER_ID,
        records=records,
        raw_model_count=len(models),
    )


_UNITS = (
    ("prompt", "per_1m_input_tokens", True),
    ("completion", "per_1m_output_tokens", True),
    ("input_cache_read", "per_1m_input_cache_read_tokens", True),
    ("image", "per_image", False),
    ("request", "per_request", False),
)


def _extract_units(bracket: dict) -> list[tuple[str, float, bool]]:
    out = []
    for src_key, unit, scale in _UNITS:
        raw = bracket.get(src_key)
        if raw is None:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 0:
            out.append((unit, v, scale))
    return out


def _pick_base_bracket(brackets: list[dict]) -> dict:
    """Pick the bracket without a min_context — the base price advertised on /models."""
    for b in brackets:
        if "min_context" not in b:
            return b
    return brackets[0]


def _rec(model_id: str, unit: str, price: float) -> PriceRecord:
    return PriceRecord(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        raw_model_name=model_id,
        channel_type="aggregator",
        unit=unit,  # type: ignore[arg-type]
        price_usd=price,
        source_url=DISPLAY_URL,
        method="json-api",
    )
