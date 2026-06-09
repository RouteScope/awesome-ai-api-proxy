"""UiUiAPI — new-api fork. Thin wrapper over fetchers._new_api.

API console subdomain: api1.uiuiapi.com (the marketing site uiuiapi.com is just
a static landing page; the real new-api install is on api1.).
"""

from __future__ import annotations

from ._common import FetchResult
from ._new_api import fetch_new_api

PROVIDER_ID = "uiuiapi"
PROVIDER_NAME = "UiUiAPI"
SOURCE_URL = "https://api1.uiuiapi.com/api/pricing"
DISPLAY_URL = "https://uiuiapi.com"


def fetch() -> FetchResult:
    return fetch_new_api(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        pricing_api_url=SOURCE_URL,
        public_pricing_url=DISPLAY_URL,
        channel_type="official-relay",
    )
