"""Compile the latest day's snapshots into prices.latest.json + README tables.

Steps:
1. Find the newest data/snapshots/<date>/ dir
2. Load every <fetcher>.json (skip .error.json — they're handled by the PR body)
3. Resolve each PriceRecord against data/canonical-models.yaml (alias → canonical)
4. Write data/prices.latest.json (flat normalized list, with canonical resolved)
5. Render the README price table between <!-- prices:start --> markers in all 3 READMEs
6. Render docs/prices.md (full table: every model seen, canonical or not)
7. Append a summary line to data/prices.history.jsonl

Run after `python -m scripts.scrape`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console

from ._paths import (
    CANONICAL_YAML,
    PRICES_DOC,
    PRICES_HISTORY,
    PRICES_LATEST,
    READMES,
    SNAPSHOTS_DIR,
)

console = Console()

PROVIDER_COLUMN_ORDER = ["openrouter", "atlascloud", "relaydance"]
START_MARKER = "<!-- prices:start -->"
END_MARKER = "<!-- prices:end -->"


def _latest_snapshot_dir() -> Path:
    dirs = sorted(p for p in SNAPSHOTS_DIR.iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError(f"No snapshot dir under {SNAPSHOTS_DIR}; run scripts.scrape first.")
    return dirs[-1]


def _load_canonical() -> dict:
    return yaml.safe_load(CANONICAL_YAML.read_text(encoding="utf-8"))


def _build_alias_index(canonical_doc: dict) -> dict[str, dict]:
    """Map every alias (lowercased) → its canonical entry."""
    out: dict[str, dict] = {}
    for entry in canonical_doc.get("canonical_models", []):
        for alias in entry.get("aliases", []) or []:
            out[alias.lower()] = entry
        # Also auto-map the canonical name itself.
        out[entry["canonical"].lower()] = entry
    return out


def _load_snapshots(snapshot_dir: Path) -> list[dict]:
    """Flatten every fetcher's records, drop .error.json files."""
    flat: list[dict] = []
    for path in sorted(snapshot_dir.glob("*.json")):
        if path.name.endswith(".error.json"):
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        flat.extend(result.get("records", []))
    return flat


def _resolve_canonical(records: list[dict], alias_index: dict[str, dict]) -> list[dict]:
    """Mutate each record with canonical_model / model_family / tier when alias matches."""
    for rec in records:
        raw = rec.get("raw_model_name", "")
        # Try full match, then strip the vendor prefix.
        candidates = [raw, raw.split("/", 1)[-1], raw.split(":", 1)[0]]
        for c in candidates:
            entry = alias_index.get(c.lower())
            if entry:
                rec["canonical_model"] = entry["canonical"]
                rec["model_family"] = entry.get("family")
                rec["tier"] = entry.get("tier")
                break
    return records


def _write_prices_latest(records: list[dict], snapshot_date: str) -> None:
    PRICES_LATEST.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshot_date": snapshot_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "record_count": len(records),
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _append_history(records: list[dict], snapshot_date: str) -> None:
    provider_counts: dict[str, int] = defaultdict(int)
    canonical_seen: set[str] = set()
    for rec in records:
        provider_counts[rec["provider_id"]] += 1
        if rec.get("canonical_model"):
            canonical_seen.add(rec["canonical_model"])
    line = (
        json.dumps(
            {
                "snapshot_date": snapshot_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "record_count": len(records),
                "providers": dict(provider_counts),
                "canonical_models_seen": sorted(canonical_seen),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    with PRICES_HISTORY.open("a", encoding="utf-8") as f:
        f.write(line)


def _format_price(price: float) -> str:
    if price >= 10:
        return f"${price:.2f}"
    if price >= 1:
        return f"${price:.3f}"
    if price >= 0.01:
        return f"${price:.3f}"
    return f"${price:.4f}"


def _build_tier_tables(
    records: list[dict], canonical_doc: dict, snapshot_date: str
) -> str:
    """Render markdown tables grouped by tier."""
    canonical_models = canonical_doc.get("canonical_models", [])
    # Index: (canonical, unit, provider_id) -> price
    matrix: dict[tuple[str, str, str], float] = {}
    for rec in records:
        cm = rec.get("canonical_model")
        if not cm:
            continue
        key = (cm, rec["unit"], rec["provider_id"])
        # Keep the first record per cell (snapshots are flat; no aggregation needed today).
        matrix.setdefault(key, rec["price_usd"])

    providers_in_use = [p for p in PROVIDER_COLUMN_ORDER if any(p == k[2] for k in matrix)]

    def render_row(model: dict, unit: str) -> str:
        cells = [f"`{model['canonical']}`"]
        # Use OpenRouter's observed price as the reference (it's the closest objective
        # baseline we have — officially-authorized, ~5% markup). ⚠ if relay < 50% of OR.
        or_price = matrix.get((model["canonical"], unit, "openrouter"))
        for pid in providers_in_use:
            price = matrix.get((model["canonical"], unit, pid))
            if price is None:
                cells.append("—")
                continue
            cell = _format_price(price)
            if pid != "openrouter" and or_price and price < or_price * 0.5:
                cell += " ⚠"
            cells.append(cell)
        return "| " + " | ".join(cells) + " |"

    def render_tier_table(tier: int, unit: str, header_suffix: str) -> str:
        rows = []
        for model in canonical_models:
            if model.get("tier") != tier:
                continue
            # only render rows where at least one provider has data for this unit
            cm = model["canonical"]
            if not any(k[0] == cm and k[1] == unit for k in matrix):
                continue
            rows.append(render_row(model, unit))
        if not rows:
            return ""
        provider_names = {
            "openrouter": "OpenRouter (ref)",
            "atlascloud": "Atlas Cloud",
            "relaydance": "Relaydance",
        }
        header = (
            "| Model | "
            + " | ".join(provider_names.get(p, p) for p in providers_in_use)
            + " |"
        )
        align = "|---" * (1 + len(providers_in_use)) + "|"
        title = {
            1: "### Tier 1 — cheapest viable (routine, batch summaries)",
            2: "### Tier 2 — daily driver (agent, coding)",
            3: "### Tier 3 — top frontier (hardest problems)",
            4: "### Tier 4 — multimodal (different units, can't compare to text)",
        }[tier]
        return (
            f"{title} — {header_suffix}\n\n"
            + header
            + "\n"
            + align
            + "\n"
            + "\n".join(rows)
            + "\n"
        )

    chunks = []
    for tier in (1, 2, 3):
        chunk = render_tier_table(tier, "per_1m_input_tokens", "USD per 1M input tokens")
        if chunk:
            chunks.append(chunk)
    # Tier 4: render per-unit rows individually because each multimodal model has its own unit.
    tier4_models = [m for m in canonical_models if m.get("tier") == 4]
    if tier4_models:
        rows = []
        for model in tier4_models:
            cm = model["canonical"]
            units_seen = sorted({k[1] for k in matrix if k[0] == cm})
            for unit in units_seen:
                pretty_unit = {
                    "per_second": "USD per second",
                    "per_image": "USD per image",
                    "per_request": "USD per request",
                    "per_1m_input_tokens": "USD per 1M input tokens",
                    "per_1m_output_tokens": "USD per 1M output tokens",
                    "per_1m_input_cache_read_tokens": "USD per 1M cache-read tokens",
                }.get(unit, unit)
                cells = [f"`{cm}`", pretty_unit]
                for pid in providers_in_use:
                    price = matrix.get((cm, unit, pid))
                    cells.append(_format_price(price) if price is not None else "—")
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            provider_names = {
                "openrouter": "OpenRouter (ref)",
                "atlascloud": "Atlas Cloud",
                "relaydance": "Relaydance",
            }
            header = (
                "| Model | Unit | "
                + " | ".join(provider_names.get(p, p) for p in providers_in_use)
                + " |"
            )
            align = "|---" * (2 + len(providers_in_use)) + "|"
            chunks.append(
                "### Tier 4 — multimodal (different units, can't compare to text)\n\n"
                + header
                + "\n"
                + align
                + "\n"
                + "\n".join(rows)
                + "\n"
            )

    snapshot_count = len(records)
    intro = (
        f"_Snapshot date: **{snapshot_date}**. {snapshot_count} price records across "
        f"{len(providers_in_use)} fetched providers. **Reference column** is OpenRouter "
        f"(officially-authorized, ~5% markup). ⚠ = relay quotes <50% of OpenRouter — "
        f"verify with [canary prompts](docs/canary-prompts.md) before trusting._\n\n"
    )
    outro = (
        "\n_Full per-model breakdown (including non-canonical models): "
        "[`docs/prices.md`](docs/prices.md). "
        "Raw snapshots: [`data/snapshots/`](data/snapshots/). "
        "Machine-readable: [`data/prices.latest.json`](data/prices.latest.json)._\n"
    )
    return intro + "\n".join(chunks) + outro


def _update_readme(readme_path: Path, body: str) -> bool:
    if not readme_path.exists():
        return False
    text = readme_path.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        return False
    start = text.index(START_MARKER) + len(START_MARKER)
    end = text.index(END_MARKER)
    new_text = text[:start] + "\n" + body + "\n" + text[end:]
    readme_path.write_text(new_text, encoding="utf-8")
    return True


def _build_full_doc(records: list[dict], snapshot_date: str) -> str:
    """docs/prices.md — every model, sorted by provider then model."""
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_provider[rec["provider_id"]].append(rec)

    lines = [
        "# Full price snapshot",
        "",
        f"_Generated from `data/snapshots/{snapshot_date}/` by `scripts/build_prices.py`._  ",
        f"_Snapshot date: **{snapshot_date}**. Machine-readable source: [`data/prices.latest.json`](../data/prices.latest.json)._",
        "",
        "For the curated tier-ladder comparison, see the README. This page is the full dump — every model surface, no curation.",
        "",
    ]
    for pid in sorted(by_provider):
        recs = by_provider[pid]
        provider_name = recs[0]["provider_name"]
        source = recs[0]["source_url"]
        lines.append(f"## {provider_name} — `{pid}`")
        lines.append("")
        lines.append(f"Source: <{source}> · Records: {len(recs)}")
        lines.append("")
        lines.append("| Model | Canonical | Unit | Price (USD) |")
        lines.append("|---|---|---|---|")
        for rec in sorted(recs, key=lambda r: (r["raw_model_name"], r["unit"])):
            lines.append(
                "| `{model}` | {canon} | {unit} | {price} |".format(
                    model=rec["raw_model_name"],
                    canon=f"`{rec['canonical_model']}`" if rec.get("canonical_model") else "—",
                    unit=rec["unit"],
                    price=_format_price(rec["price_usd"]),
                )
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    snapshot_dir = _latest_snapshot_dir()
    snapshot_date = snapshot_dir.name
    console.rule(f"[bold]Building prices from {snapshot_dir}")

    canonical_doc = _load_canonical()
    alias_index = _build_alias_index(canonical_doc)
    console.print(f"canonical aliases indexed: {len(alias_index)}")

    records = _load_snapshots(snapshot_dir)
    console.print(f"records loaded: {len(records)}")
    if not records:
        console.print("[red]No records to compile.[/red]")
        return 1

    records = _resolve_canonical(records, alias_index)
    matched = sum(1 for r in records if r.get("canonical_model"))
    console.print(f"records resolved to a canonical model: {matched}/{len(records)}")

    _write_prices_latest(records, snapshot_date)
    console.print(f"[green]wrote[/green] {PRICES_LATEST.relative_to(SNAPSHOTS_DIR.parent.parent)}")

    _append_history(records, snapshot_date)
    console.print(f"[green]appended[/green] {PRICES_HISTORY.relative_to(SNAPSHOTS_DIR.parent.parent)}")

    table_md = _build_tier_tables(records, canonical_doc, snapshot_date)
    updated = []
    for readme in READMES:
        if _update_readme(readme, table_md):
            updated.append(readme.name)
    console.print(f"[green]updated[/green] READMEs with markers: {updated or '(none — add markers first)'}")

    PRICES_DOC.parent.mkdir(parents=True, exist_ok=True)
    PRICES_DOC.write_text(_build_full_doc(records, snapshot_date) + "\n", encoding="utf-8")
    console.print(f"[green]wrote[/green] {PRICES_DOC.relative_to(SNAPSHOTS_DIR.parent.parent)}")

    console.rule()
    console.print("[bold green]Done.[/bold green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
