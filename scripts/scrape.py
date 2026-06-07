"""Entry point: read providers.yaml, run all fetchers (or a single one), write snapshots.

Usage:
    python -m scripts.scrape                # run every fetcher
    python -m scripts.scrape openrouter     # run one
    python -m scripts.scrape atlascloud relaydance  # run several
"""

from __future__ import annotations

import sys
import traceback

import yaml
from rich.console import Console

from fetchers import get_fetcher
from fetchers._common import write_error, write_snapshot

from ._paths import PROVIDERS_YAML, SNAPSHOTS_DIR

console = Console()


def discover_fetchers() -> dict[str, str]:
    """Walk providers.yaml and return {fetcher_id: provider_name}."""
    raw = yaml.safe_load(PROVIDERS_YAML.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for section, entries in raw.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            pricing = entry.get("pricing") or {}
            fetcher = pricing.get("fetcher")
            if fetcher:
                found[fetcher] = entry.get("name", fetcher)
    return found


def run_fetcher(fetcher_id: str, display_name: str) -> bool:
    console.rule(f"[bold]{display_name} ({fetcher_id})")
    try:
        fn = get_fetcher(fetcher_id)
    except KeyError as e:
        console.print(f"[red]skip[/red]: {e}")
        return False
    try:
        result = fn()
        snapshot_path = write_snapshot(result, SNAPSHOTS_DIR)
        console.print(
            f"[green]ok[/green] {len(result.records)} records "
            f"(from {result.raw_model_count} raw models) → {snapshot_path.relative_to(SNAPSHOTS_DIR.parent.parent)}"
        )
        return True
    except Exception as exc:
        err_path = write_error(fetcher_id, exc, SNAPSHOTS_DIR)
        console.print(f"[red]fail[/red] {type(exc).__name__}: {exc}")
        console.print(f"       error log → {err_path.relative_to(SNAPSHOTS_DIR.parent.parent)}")
        console.print(traceback.format_exc(limit=3))
        return False


def main(argv: list[str]) -> int:
    available = discover_fetchers()
    if not available:
        console.print("[red]No providers in providers.yaml have a pricing.fetcher.[/red]")
        return 1

    if argv:
        requested = argv
        unknown = [f for f in requested if f not in available]
        if unknown:
            console.print(f"[red]Unknown fetcher(s):[/red] {unknown}")
            console.print(f"available: {sorted(available)}")
            return 2
        to_run = [(f, available[f]) for f in requested]
    else:
        to_run = sorted(available.items())

    failures = 0
    for fid, name in to_run:
        if not run_fetcher(fid, name):
            failures += 1

    console.rule()
    console.print(f"Done. {len(to_run) - failures}/{len(to_run)} fetchers succeeded.")
    return 0 if failures == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
