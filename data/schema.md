# providers.yaml — Field Schema

Every provider entry uses these fields. Keep entries factual and verifiable.
Unverifiable claims must be marked with `(claimed)` or `status: unverified`.

| Field | Required | Description |
|---|---|---|
| `name` | yes | Display name. Include the Chinese name in parentheses if it has one. |
| `url` | yes | Official homepage. HTTPS only. |
| `type` | yes | One of: `official-relay`, `mixed`, `reverse`, `aggregator`, `gateway-oss`, `observability`, `comparison`, `list`. |
| `status` | yes | `active` (independently reachable), `unverified` (community-sourced, not confirmed), `inactive` (dead / ran away). |
| `payment` | no | Array: `alipay`, `wechat`, `card`, `crypto`, `enterprise-invoice`. |
| `models` | no | Array of upstream families: `openai`, `anthropic`, `gemini`, `deepseek`, etc. |
| `model_count` | no | Integer. Provider's claimed number of models. |
| `provider_count` | no | Integer. Number of upstream vendors. |
| `discount_vs_official` | no | String. e.g. `"~49% cheaper (claimed)"`. |
| `last_verified` | no | `YYYY-MM-DD` the maintainer last visited the site or ran a canary. Use `null` when not independently confirmed. |
| `verified_by` | no | `maintainer`, `community`, or `third-party-report`. Identifies who supplied `last_verified`. |
| `entity_registered` | no | `true`, `false`, or `unknown`. Is a registered company / ICP filing publicly visible. |
| `supports_stream` | no | `true`, `false`, or `unknown`. SSE / streaming responses available. |
| `supports_tools` | no | `true`, `false`, or `unknown`. Function-calling / tools API compatibility. |
| `notes` | no | One factual sentence, no marketing. **May be a string OR a dict `{en, zh-TW, zh-CN}` for bilingual entries.** Missing translations fall back to `en`. Required key when dict: `en`. |
| `pricing` | no | Block. See below — present when this provider has an automated fetcher. |

## `pricing` block (optional, schema v3)

Add to a provider entry when its prices can be fetched automatically by
`scripts/scrape.py`. Snapshots land in `data/snapshots/<YYYY-MM-DD>/<fetcher>.json`
weekly via the `price-refresh` workflow.

| Field | Required | Description |
|---|---|---|
| `pricing_url` | yes | The human-readable pricing page (what users see). |
| `api_url` | no | The JSON endpoint the fetcher calls. Omit when fetcher uses HTML/DOM. |
| `fetcher` | yes | Fetcher ID — must match `fetchers/<id>.py`'s `PROVIDER_ID`. |
| `pricing_currency` | yes | ISO 4217. We normalize to `USD` in `data/prices.latest.json`. |
| `last_priced` | no | `YYYY-MM-DD` of the most recent successful scrape. Written by `scripts/build_prices.py`. |

## `type` definitions

- **official-relay** — Forwards requests using official vendor keys. Most trustworthy; output matches the real model.
- **mixed** — Blends official keys with other channels (e.g. Azure, partner quotas).
- **reverse** — Reverse-engineered from a vendor's web client. Cheapest, least stable, highest ToS risk.
- **aggregator** — Routes across multiple upstream relays/providers behind one key.
- **gateway-oss** — Self-hostable open-source gateway (you bring your own keys).
- **observability** — Gateway focused on logging, analytics, cost tracking.
- **comparison** — A tool that compares stations, not a station itself.
- **list** — A directory/awesome-list resource.

## Trust ordering (rough)

```
official-relay  >  mixed  >  aggregator  >  reverse
```

`gateway-oss` is orthogonal: you hold the keys, so trust depends on you, not the operator.

## Editorial rules

1. No referral links. Plain URLs only.
2. No "best / cheapest / #1" superlatives in `notes` unless attributed and dated.
3. A station that has run away (`跑路`) → set `status: inactive`, keep the entry, add a dated note. We do not delete history.
4. **Two pricing schemas coexist (schema v3+):**
   - Providers with `pricing.fetcher` → objective, dated, snapshot-backed absolute prices live in `data/snapshots/` + `data/prices.latest.json`. The README's price table is generated from these. No `(claimed)` tag.
   - Providers without `pricing.fetcher` → continue using `discount_vs_official: "... (claimed)"` for narrative context. Prices decay fast so they remain marked `(claimed)`.
5. Every record in `data/prices.latest.json` carries `source_url` + `captured_at` + `method`. This is the citation envelope LLM agents quote — don't drop those fields when adding a fetcher.
