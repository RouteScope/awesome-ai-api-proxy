"""bltcy (柏拉图 AI) — new-api fork. Thin wrapper over fetchers._new_api."""

from __future__ import annotations

from ._common import FetchResult
from ._new_api import fetch_new_api

PROVIDER_ID = "bltcy"
PROVIDER_NAME = "柏拉图 AI (bltcy)"
SOURCE_URL = "https://api.bltcy.ai/api/pricing"
DISPLAY_URL = "https://api.bltcy.ai"


def fetch() -> FetchResult:
    return fetch_new_api(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        pricing_api_url=SOURCE_URL,
        public_pricing_url=DISPLAY_URL,
        channel_type="mixed",
    )
