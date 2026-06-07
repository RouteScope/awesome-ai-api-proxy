"""Generate SVG charts from data/prices.latest.json.

Output goes to assets/charts/*.svg. Charts are embedded in the README between
the price-table markers so readers see the cost spread at a glance.

Run after `python -m scripts.build_prices`. Idempotent — overwrites existing SVGs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # No display needed; SVG output only.
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.colors import LogNorm
from rich.console import Console

from ._paths import CANONICAL_YAML, PRICES_LATEST, REPO_ROOT

console = Console()

CHARTS_DIR = REPO_ROOT / "assets" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

PROVIDER_COLORS = {
    "openrouter": "#7c3aed",  # purple
    "atlascloud": "#0ea5e9",  # sky
    "relaydance": "#10b981",  # emerald
}
PROVIDER_LABELS = {
    "openrouter": "OpenRouter (ref)",
    "atlascloud": "Atlas Cloud",
    "relaydance": "Relaydance",
}


def _load() -> tuple[list[dict], list[dict]]:
    prices = json.loads(PRICES_LATEST.read_text(encoding="utf-8"))
    canonical = yaml.safe_load(CANONICAL_YAML.read_text(encoding="utf-8")).get(
        "canonical_models", []
    )
    return prices, canonical


def _matrix(records: list[dict], unit: str) -> dict[tuple[str, str], float]:
    """Index price by (canonical, provider) for a given unit."""
    out: dict[tuple[str, str], float] = {}
    for rec in records:
        cm = rec.get("canonical_model")
        if not cm or rec.get("unit") != unit:
            continue
        out.setdefault((cm, rec["provider_id"]), rec["price_usd"])
    return out


def chart_tier_ladder(prices_doc: dict, canonical: list[dict], unit: str, kind: str) -> Path:
    """Grouped bar chart: x=canonical models (sorted by tier), y=log $ per unit."""
    records = prices_doc["records"]
    matrix = _matrix(records, unit)
    snapshot_date = prices_doc.get("snapshot_date", "")

    # Keep canonical models with at least one observation in this unit.
    models_in_unit = [
        m for m in canonical
        if (m.get("tier") or 5) <= 3  # Tier 1-3 for text token charts
        and any(k[0] == m["canonical"] for k in matrix)
    ]
    models_in_unit.sort(key=lambda m: (m.get("tier", 99), m["canonical"]))
    if not models_in_unit:
        console.print(f"[yellow]no data for unit={unit}; skip[/yellow]")
        return CHARTS_DIR / f"tier-ladder-{kind}.svg"

    providers = sorted({k[1] for k in matrix})
    providers = [p for p in PROVIDER_COLORS if p in providers]  # stable order

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
    n_models = len(models_in_unit)
    n_providers = len(providers)
    bar_width = 0.8 / n_providers
    x = np.arange(n_models)

    for i, pid in enumerate(providers):
        heights = [matrix.get((m["canonical"], pid)) for m in models_in_unit]
        # Replace None with 0 for plotting but track which were missing.
        plot_heights = [h if h is not None else 0 for h in heights]
        offset = (i - (n_providers - 1) / 2) * bar_width
        bars = ax.bar(
            x + offset,
            plot_heights,
            bar_width,
            label=PROVIDER_LABELS.get(pid, pid),
            color=PROVIDER_COLORS.get(pid, "#888"),
            edgecolor="white",
            linewidth=0.5,
        )
        # Annotate bars
        for bar, h in zip(bars, heights):
            if h is None:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.05,
                f"${h:.2f}" if h >= 1 else f"${h:.3f}",
                ha="center",
                va="bottom",
                fontsize=7.5,
                color="#555",
            )

    # Tier separators
    last_tier = None
    for i, m in enumerate(models_in_unit):
        if last_tier is not None and m.get("tier") != last_tier:
            ax.axvline(i - 0.5, color="#ddd", linestyle="--", linewidth=0.8, zorder=0)
        last_tier = m.get("tier")

    ax.set_xticks(x)
    ax.set_xticklabels(
        [m["canonical"] for m in models_in_unit],
        rotation=30,
        ha="right",
        fontsize=9,
    )
    ax.set_yscale("log")
    ax.set_ylabel(f"USD per {'1M input' if kind == 'input' else '1M output'} tokens (log)", fontsize=10)
    ax.set_title(
        f"Cost-tier ladder: canonical models, {kind} pricing  ·  snapshot {snapshot_date}",
        fontsize=11,
        pad=12,
    )
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, color="#ccc")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    plt.tight_layout()

    out = CHARTS_DIR / f"tier-ladder-{kind}.svg"
    plt.savefig(out, format="svg", bbox_inches="tight")
    plt.close(fig)
    return out


def chart_spread_heatmap(prices_doc: dict, canonical: list[dict], unit: str, kind: str) -> Path:
    """Heatmap: rows=canonical models, cols=providers, color=log price."""
    records = prices_doc["records"]
    matrix = _matrix(records, unit)
    snapshot_date = prices_doc.get("snapshot_date", "")

    models = [m for m in canonical if any(k[0] == m["canonical"] for k in matrix)]
    models.sort(key=lambda m: (m.get("tier", 99), m["canonical"]))
    providers = [p for p in PROVIDER_COLORS if any(k[1] == p for k in matrix)]
    if not models or not providers:
        return CHARTS_DIR / f"spread-heatmap-{kind}.svg"

    grid = np.full((len(models), len(providers)), np.nan)
    for i, m in enumerate(models):
        for j, p in enumerate(providers):
            v = matrix.get((m["canonical"], p))
            if v is not None:
                grid[i, j] = v

    fig, ax = plt.subplots(figsize=(6.5, max(3, 0.45 * len(models) + 1.5)), dpi=110)
    masked = np.ma.masked_invalid(grid)
    cmap = plt.cm.viridis_r
    cmap.set_bad(color="#f3f4f6")

    vmin = max(np.nanmin(grid), 1e-3)
    vmax = np.nanmax(grid)
    im = ax.imshow(
        masked,
        aspect="auto",
        cmap=cmap,
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )

    for i in range(len(models)):
        for j in range(len(providers)):
            v = grid[i, j]
            if not np.isnan(v):
                color = "white" if v > vmin * 30 else "#222"
                ax.text(
                    j, i, f"${v:.2f}" if v >= 1 else f"${v:.3f}",
                    ha="center", va="center", fontsize=8.5, color=color,
                )
            else:
                ax.text(j, i, "—", ha="center", va="center", fontsize=10, color="#9ca3af")

    ax.set_xticks(np.arange(len(providers)))
    ax.set_xticklabels([PROVIDER_LABELS.get(p, p) for p in providers], fontsize=9)
    ax.set_yticks(np.arange(len(models)))
    ax.set_yticklabels(
        [f"T{m.get('tier', '?')}  {m['canonical']}" for m in models],
        fontsize=9,
    )
    ax.set_title(
        f"Cost spread heatmap, {kind} pricing  ·  snapshot {snapshot_date}",
        fontsize=10.5,
        pad=10,
    )

    cbar = plt.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label(f"USD per 1M {kind} tokens (log)", fontsize=8.5)
    cbar.ax.tick_params(labelsize=7.5)

    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    plt.tight_layout()

    out = CHARTS_DIR / f"spread-heatmap-{kind}.svg"
    plt.savefig(out, format="svg", bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    prices_doc, canonical = _load()
    written: list[Path] = []
    for unit, kind in (
        ("per_1m_input_tokens", "input"),
        ("per_1m_output_tokens", "output"),
    ):
        ladder = chart_tier_ladder(prices_doc, canonical, unit, kind)
        heatmap = chart_spread_heatmap(prices_doc, canonical, unit, kind)
        written += [ladder, heatmap]
    console.rule("[bold green]Charts built")
    for p in written:
        console.print(f"  {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
