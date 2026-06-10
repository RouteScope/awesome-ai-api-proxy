"""Auto-generate provider tables in the three READMEs from data/providers.yaml.

Fixes two long-standing problems at once:
1. The China relays table was 7 columns, which squeezed Notes into 3-4 lines per
   row on GitHub's render. Reduces to 5 columns (Station / Type / Payment /
   Trust / Notes) — Notes now reads in one line for most entries.
2. Every prior provider PR had to hand-edit three READMEs alongside
   providers.yaml. Now PRs only touch providers.yaml; tables regenerate.

`notes` in providers.yaml can be either a string (English-only) or a dict
{en, zh-TW, zh-CN} for bilingual entries. Missing translations fall back to en.

Tables sit between `<!-- providers:<section>:start -->` and `:end -->` markers
in each README. Sections supported: china_relays, global_gateways,
self_hosted_alternatives, comparison_tools.

Run after editing providers.yaml. Idempotent.
"""

from __future__ import annotations

import yaml
from rich.console import Console

from ._paths import PROVIDERS_YAML, READMES, REPO_ROOT

console = Console()

LANGS_BY_FILE = {
    "README.md": "en",
    "README.zh-TW.md": "zh-TW",
    "README.zh-CN.md": "zh-CN",
}

PAYMENT_LABELS = {
    "en": {
        "alipay": "Alipay", "wechat": "WeChat", "card": "Card",
        "crypto": "Crypto", "enterprise-invoice": "Invoice",
    },
    "zh-TW": {
        "alipay": "支付寶", "wechat": "微信", "card": "卡",
        "crypto": "加密貨幣", "enterprise-invoice": "對公",
    },
    "zh-CN": {
        "alipay": "支付宝", "wechat": "微信", "card": "卡",
        "crypto": "加密货币", "enterprise-invoice": "对公",
    },
}

SECTION_HEADERS = {
    "china_relays": {
        "en": ["Station", "Type", "Payment", "Trust", "Notes"],
        "zh-TW": ["中轉站", "類型", "支付", "信任", "備註"],
        "zh-CN": ["中转站", "类型", "支付", "信任", "备注"],
    },
    "global_gateways": {
        "en": ["Service", "Type", "Payment", "Notes"],
        "zh-TW": ["服務", "類型", "支付", "備註"],
        "zh-CN": ["服务", "类型", "支付", "备注"],
    },
    "self_hosted_alternatives": {
        "en": ["Project", "Type", "Notes"],
        "zh-TW": ["專案", "類型", "備註"],
        "zh-CN": ["项目", "类型", "备注"],
    },
    "comparison_tools": {
        "en": ["Tool", "Notes"],
        "zh-TW": ["工具", "備註"],
        "zh-CN": ["工具", "备注"],
    },
}

TRUST_TEMPLATE = {
    "en": {
        "active": "active",
        "unverified": "unverified",
        "inactive": "inactive",
        "registered_suffix": " · registered",
        "date_prefix": " · ",
    },
    "zh-TW": {
        "active": "active", "unverified": "unverified", "inactive": "inactive",
        "registered_suffix": " · 已註冊", "date_prefix": " · ",
    },
    "zh-CN": {
        "active": "active", "unverified": "unverified", "inactive": "inactive",
        "registered_suffix": " · 已注册", "date_prefix": " · ",
    },
}

# Per-status emoji prefix on the Station/Service cell.
# 🟢 maintainer-verified active · 🟡 community-listed or unverified · 🔴 inactive
STATUS_EMOJI = {
    "active": "🟢",      # adjusted to 🟡 below if verified_by != maintainer
    "unverified": "🟡",
    "inactive": "🔴",
}

# Risk flag short labels, per language. Brief on purpose — these appear inside the Trust cell.
RISK_LABELS = {
    "en": {
        "operator_submitted": "operator-self",
        "no_entity": "no-entity",
        "reverse_channel": "reverse",
        "prices_too_cheap": "cheap-trap",
        "ran_away": "ran-away",
    },
    "zh-TW": {
        "operator_submitted": "自薦",
        "no_entity": "無主體",
        "reverse_channel": "逆向",
        "prices_too_cheap": "價過低",
        "ran_away": "跑路",
    },
    "zh-CN": {
        "operator_submitted": "自荐",
        "no_entity": "无主体",
        "reverse_channel": "逆向",
        "prices_too_cheap": "价过低",
        "ran_away": "跑路",
    },
}


def _notes_for(entry: dict, lang: str) -> str:
    notes = entry.get("notes") or ""
    if isinstance(notes, dict):
        return notes.get(lang) or notes.get("en") or ""
    return notes


def _payments_cell(entry: dict, lang: str) -> str:
    payments = entry.get("payment") or []
    labels = PAYMENT_LABELS[lang]
    if not payments:
        return "—"
    return "/".join(labels.get(p, p) for p in payments)


def _trust_cell(entry: dict, lang: str) -> str:
    tmpl = TRUST_TEMPLATE[lang]
    status = entry.get("status", "unverified")
    parts = [tmpl.get(status, status)]
    last_verified = entry.get("last_verified")
    if last_verified and status == "active":
        parts.append(f"{tmpl['date_prefix']}{last_verified}")
    if entry.get("entity_registered") is True:
        parts.append(tmpl["registered_suffix"])
    flags = entry.get("risk_flags") or []
    if flags:
        labels = RISK_LABELS[lang]
        rendered = ", ".join(labels.get(f, f) for f in flags)
        parts.append(f" · ⚠ {rendered}")
    return "".join(parts)


def _status_emoji(entry: dict) -> str:
    """Pick a status emoji. `active + verified_by maintainer` → 🟢; other active → 🟡; etc."""
    status = entry.get("status", "unverified")
    if status == "active" and entry.get("verified_by") != "maintainer":
        return "🟡"  # active but only community-verified — slightly less trusted
    return STATUS_EMOJI.get(status, "🟡")


def _station_cell(entry: dict) -> str:
    return f"{_status_emoji(entry)} [{entry['name']}]({entry['url']})"


def _render_china_row(entry: dict, lang: str) -> str:
    return "| {station} | {type} | {payment} | {trust} | {notes} |".format(
        station=_station_cell(entry),
        type=entry.get("type", "?"),
        payment=_payments_cell(entry, lang),
        trust=_trust_cell(entry, lang),
        notes=_notes_for(entry, lang),
    )


def _render_global_row(entry: dict, lang: str) -> str:
    return "| {svc} | {type} | {payment} | {notes} |".format(
        svc=_station_cell(entry),
        type=entry.get("type", "?"),
        payment=_payments_cell(entry, lang),
        notes=_notes_for(entry, lang),
    )


def _render_self_hosted_row(entry: dict, lang: str) -> str:
    return "| {proj} | {type} | {notes} |".format(
        proj=_station_cell(entry),
        type=entry.get("type", "?"),
        notes=_notes_for(entry, lang),
    )


def _render_comparison_row(entry: dict, lang: str) -> str:
    return "| {tool} | {notes} |".format(
        tool=_station_cell(entry),
        notes=_notes_for(entry, lang),
    )


ROW_RENDERERS = {
    "china_relays": _render_china_row,
    "global_gateways": _render_global_row,
    "self_hosted_alternatives": _render_self_hosted_row,
    "comparison_tools": _render_comparison_row,
}


def _render_section(section: str, entries: list[dict], lang: str) -> str:
    headers = SECTION_HEADERS[section][lang]
    header_row = "| " + " | ".join(headers) + " |"
    align_row = "|" + "|".join(["---"] * len(headers)) + "|"
    rows = [ROW_RENDERERS[section](e, lang) for e in entries if isinstance(e, dict)]
    return "\n".join([header_row, align_row, *rows])


def _update_markers(readme_text: str, section: str, body: str) -> tuple[str, bool]:
    start_marker = f"<!-- providers:{section}:start -->"
    end_marker = f"<!-- providers:{section}:end -->"
    if start_marker not in readme_text or end_marker not in readme_text:
        return readme_text, False
    start = readme_text.index(start_marker) + len(start_marker)
    end = readme_text.index(end_marker)
    new_text = readme_text[:start] + "\n" + body + "\n" + readme_text[end:]
    return new_text, True


def main() -> int:
    doc = yaml.safe_load(PROVIDERS_YAML.read_text(encoding="utf-8"))
    sections_present = [s for s in SECTION_HEADERS if s in doc]
    console.print(f"sections to render: {sections_present}")

    updates = 0
    for readme_path in READMES:
        lang = LANGS_BY_FILE.get(readme_path.name)
        if not lang or not readme_path.exists():
            continue
        text = readme_path.read_text(encoding="utf-8")
        original = text
        for section in sections_present:
            entries = doc.get(section) or []
            if not entries:
                continue
            body = _render_section(section, entries, lang)
            text, updated = _update_markers(text, section, body)
            if updated:
                updates += 1
        if text != original:
            readme_path.write_text(text, encoding="utf-8")
            console.print(f"[green]updated[/green] {readme_path.relative_to(REPO_ROOT)}")
        else:
            console.print(f"[yellow]no markers found in[/yellow] {readme_path.relative_to(REPO_ROOT)}")
    console.rule()
    console.print(f"[bold green]Done.[/bold green] {updates} section block(s) updated across READMEs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
