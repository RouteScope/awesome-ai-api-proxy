"""OpenRouter — public /api/v1/models endpoint, no auth.

This is the canonical "clean" reference: official-authorized routing, ~5% markup
over upstream. Useful as the spread baseline against cheap relays.
"""

from __future__ import annotations

from ._common import FetchResult, PriceRecord, http_client, per_token_to_per_1m

PROVIDER_ID = "openrouter"
PROVIDER_NAME = "OpenRouter"
SOURCE_URL = "https://openrouter.ai/api/v1/models"


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
        pricing = m.get("pricing") or {}
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        if prompt is not None and float(prompt) > 0:
            records.append(
                PriceRecord(
                    provider_id=PROVIDER_ID,
                    provider_name=PROVIDER_NAME,
                    raw_model_name=model_id,
                    channel_type="aggregator",
                    unit="per_1m_input_tokens",
                    price_usd=per_token_to_per_1m(prompt),
                    source_url=SOURCE_URL,
                    method="json-api",
                )
            )
        if completion is not None and float(completion) > 0:
            records.append(
                PriceRecord(
                    provider_id=PROVIDER_ID,
                    provider_name=PROVIDER_NAME,
                    raw_model_name=model_id,
                    channel_type="aggregator",
                    unit="per_1m_output_tokens",
                    price_usd=per_token_to_per_1m(completion),
                    source_url=SOURCE_URL,
                    method="json-api",
                )
            )
        image = pricing.get("image")
        if image is not None and float(image) > 0:
            records.append(
                PriceRecord(
                    provider_id=PROVIDER_ID,
                    provider_name=PROVIDER_NAME,
                    raw_model_name=model_id,
                    channel_type="aggregator",
                    unit="per_image",
                    price_usd=float(image),
                    source_url=SOURCE_URL,
                    method="json-api",
                )
            )

    return FetchResult(
        provider_id=PROVIDER_ID,
        records=records,
        raw_model_count=len(models),
    )
