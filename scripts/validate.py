"""Schema / sanity checks for data/*.

Used by CI on PRs and also as a final gate in the weekly workflow.
Exit code 0 = OK, 1 = problems found.
"""

from __future__ import annotations

import json
import sys

import yaml
from rich.console import Console

from ._paths import CANONICAL_YAML, PRICES_LATEST, PROVIDERS_YAML

console = Console()

REQUIRED_PROVIDER_FIELDS = {"name", "url", "type", "status"}
ALLOWED_TYPES = {
    "official-relay",
    "mixed",
    "reverse",
    "aggregator",
    "gateway-oss",
    "observability",
    "comparison",
    "list",
}
ALLOWED_STATUS = {"active", "unverified", "inactive"}
ALLOWED_RISK_FLAGS = {
    "operator_submitted",
    "no_entity",
    "reverse_channel",
    "prices_too_cheap",
    "ran_away",
}
ALLOWED_UNITS = {
    "per_1m_input_tokens",
    "per_1m_output_tokens",
    "per_1m_input_cache_read_tokens",
    "per_image",
    "per_second",
    "per_request",
}


def _problem(messages: list[str], msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")
    messages.append(msg)


_REQUIRED_SUBMITTED_FIELDS = {
    "canonical_model", "unit", "price_usd", "source_url",
    "captured_at", "submitted_by", "verified_by",
}


def _validate_submitted_prices(problems: list[str], section: str, entry: dict, submitted: list) -> None:
    name = entry.get("name", "?")
    for i, sp in enumerate(submitted):
        if not isinstance(sp, dict):
            _problem(problems, f"{section}: '{name}' submitted_prices[{i}] is not a dict")
            continue
        missing = _REQUIRED_SUBMITTED_FIELDS - sp.keys()
        if missing:
            _problem(problems, f"{section}: '{name}' submitted_prices[{i}] missing: {sorted(missing)}")
        if sp.get("unit") not in ALLOWED_UNITS:
            _problem(problems, f"{section}: '{name}' submitted_prices[{i}] invalid unit: {sp.get('unit')!r}")
        price = sp.get("price_usd")
        if price is None or not (isinstance(price, (int, float)) and 0 < price < 1000):
            _problem(problems, f"{section}: '{name}' submitted_prices[{i}] suspicious price_usd: {price!r}")


def validate_providers(problems: list[str]) -> None:
    raw = yaml.safe_load(PROVIDERS_YAML.read_text(encoding="utf-8"))
    for section, entries in raw.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            missing = REQUIRED_PROVIDER_FIELDS - entry.keys()
            if missing:
                _problem(problems, f"{section}: '{entry.get('name', '?')}' missing fields: {missing}")
            if entry.get("type") not in ALLOWED_TYPES:
                _problem(problems, f"{section}: '{entry['name']}' has invalid type: {entry.get('type')!r}")
            if entry.get("status") not in ALLOWED_STATUS:
                _problem(problems, f"{section}: '{entry['name']}' has invalid status: {entry.get('status')!r}")
            risk_flags = entry.get("risk_flags") or []
            if not isinstance(risk_flags, list):
                _problem(problems, f"{section}: '{entry['name']}' risk_flags must be a list")
            else:
                for flag in risk_flags:
                    if flag not in ALLOWED_RISK_FLAGS:
                        _problem(problems, f"{section}: '{entry['name']}' has invalid risk_flag: {flag!r} (allowed: {sorted(ALLOWED_RISK_FLAGS)})")
            pricing = entry.get("pricing")
            if pricing:
                # pricing_url + pricing_currency always required; fetcher optional
                # when submitted_prices is present (manual-only providers).
                for required in ("pricing_url", "pricing_currency"):
                    if required not in pricing:
                        _problem(
                            problems,
                            f"{section}: '{entry['name']}' pricing block missing '{required}'",
                        )
                if "fetcher" not in pricing and not pricing.get("submitted_prices"):
                    _problem(
                        problems,
                        f"{section}: '{entry['name']}' pricing block needs either 'fetcher' or 'submitted_prices'",
                    )
                _validate_submitted_prices(problems, section, entry, pricing.get("submitted_prices") or [])
            notes = entry.get("notes")
            if notes is not None and not isinstance(notes, (str, dict)):
                _problem(problems, f"{section}: '{entry['name']}' notes must be string or dict")
            if isinstance(notes, dict) and "en" not in notes:
                _problem(problems, f"{section}: '{entry['name']}' bilingual notes must include 'en' key")


def validate_canonical(problems: list[str]) -> None:
    doc = yaml.safe_load(CANONICAL_YAML.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for entry in doc.get("canonical_models", []):
        cm = entry.get("canonical")
        if not cm:
            _problem(problems, f"canonical model missing 'canonical' field: {entry}")
            continue
        if cm in seen:
            _problem(problems, f"duplicate canonical name: {cm}")
        seen.add(cm)
        if entry.get("tier") not in (1, 2, 3, 4):
            _problem(problems, f"canonical {cm} has invalid tier: {entry.get('tier')!r}")


def validate_prices(problems: list[str]) -> None:
    if not PRICES_LATEST.exists():
        console.print("[yellow]![/yellow] prices.latest.json missing — skip (run build_prices first)")
        return
    doc = json.loads(PRICES_LATEST.read_text(encoding="utf-8"))
    if "records" not in doc:
        _problem(problems, "prices.latest.json missing 'records'")
        return
    for i, rec in enumerate(doc["records"]):
        for required in ("provider_id", "raw_model_name", "unit", "price_usd", "source_url", "captured_at", "method"):
            if required not in rec:
                _problem(problems, f"record[{i}] missing '{required}'")
        if rec.get("unit") not in ALLOWED_UNITS:
            _problem(problems, f"record[{i}] has invalid unit: {rec.get('unit')!r}")
        price = rec.get("price_usd")
        # Real-world extreme prices exist (some bltcy thinking variants at $1750/1M).
        # Keep an upper bound for sanity, but loose enough not to false-positive.
        if price is not None and not (price > 0 and price < 5000):
            _problem(problems, f"record[{i}] suspicious price_usd: {price} ({rec.get('provider_name')} / {rec.get('raw_model_name')})")


def main() -> int:
    problems: list[str] = []
    console.rule("[bold]Validate providers.yaml")
    validate_providers(problems)
    console.rule("[bold]Validate canonical-models.yaml")
    validate_canonical(problems)
    console.rule("[bold]Validate prices.latest.json")
    validate_prices(problems)
    console.rule()
    if problems:
        console.print(f"[red]{len(problems)} problem(s) found.[/red]")
        return 1
    console.print("[bold green]All validations passed.[/bold green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
