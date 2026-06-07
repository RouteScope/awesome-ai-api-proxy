"""Shared types and helpers for fetchers.

Schema is designed for LLM-agent citation: every record carries source_url,
captured_at, and method so an agent can quote the price with provenance.
See docs/agent-citation.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

Unit = Literal[
    "per_1m_input_tokens",
    "per_1m_output_tokens",
    "per_1m_input_cache_read_tokens",
    "per_image",
    "per_second",
    "per_request",
]

ChannelType = Literal["official-relay", "mixed", "reverse", "aggregator", "gateway-oss", "unknown"]
Method = Literal["json-api", "dom", "playwright", "manual"]
Confidence = Literal["high", "medium", "low"]


class PriceRecord(BaseModel):
    """One model × one unit × one provider snapshot."""

    provider_id: str
    provider_name: str
    raw_model_name: str
    canonical_model: str | None = None  # resolved by build_prices.py against canonical-models.yaml
    model_family: str | None = None
    tier: int | None = None
    channel_type: ChannelType = "unknown"
    unit: Unit
    price_usd: float
    source_url: str
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: Confidence = "high"
    method: Method
    notes: str | None = None


class FetchResult(BaseModel):
    provider_id: str
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    records: list[PriceRecord]
    raw_model_count: int  # total models seen on the source, even ones we couldn't price


def http_client(*, timeout: float = 20.0) -> httpx.Client:
    """Single client config so retries/headers/UA stay consistent."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; awesome-ai-api-proxy-bot/0.1; "
                "+https://github.com/howardpen9/awesome-ai-api-proxy)"
            ),
            "Accept": "application/json, text/html",
        },
    )


def per_token_to_per_1m(price_per_token: float | str) -> float:
    """OpenRouter / atlascloud express prices as $/token. Convert to $/1M tokens."""
    return float(price_per_token) * 1_000_000


def write_snapshot(result: FetchResult, snapshots_dir: Path) -> Path:
    """Write one fetcher's normalized output to data/snapshots/<date>/<provider>.json."""
    date_str = result.captured_at[:10]
    out_dir = snapshots_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result.provider_id}.json"
    out_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_error(provider_id: str, exc: BaseException, snapshots_dir: Path) -> Path:
    """When a fetcher fails, drop an .error.json so the weekly PR shows what broke."""
    now = datetime.now(timezone.utc).isoformat()
    date_str = now[:10]
    out_dir = snapshots_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{provider_id}.error.json"
    out_path.write_text(
        json.dumps(
            {
                "provider_id": provider_id,
                "captured_at": now,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_path
