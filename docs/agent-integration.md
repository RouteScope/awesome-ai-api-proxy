# Agent integration

How to plug the **weekly AI API relay price observatory** into LLM agents,
research scripts, or automation tools.

Every example answers the same question — *"What's the cheapest provider for
`claude-sonnet-4.6` (input)?"* — so you can directly compare friction.

The data layer behind all of these is one stable file:
`https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json`

Each record carries `provider_id`, `raw_model_name`, `canonical_model`, `unit`,
`price_usd`, `source_url`, `captured_at`, `method` — the **citation envelope**.
Always pass `source_url` + `captured_at` through to the user so they can verify.

---

## 1. MCP server (recommended for Claude Desktop / Cline / Cursor)

Install once, then **the model picks the right tool automatically** — no glue
code per question.

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "awesome-ai-api-proxy": {
      "command": "uvx",
      "args": ["awesome-ai-api-proxy-mcp"]
    }
  }
}
```

Then in Claude Desktop:

> **You:** What's the cheapest provider for `claude-sonnet-4.6` input?
>
> **Claude (silently calls `find_cheapest("claude-sonnet-4.6")`):** Atlas Cloud
> and OpenRouter both list it at $3.00/1M tokens as of 2026-06-07
> (source: <https://www.atlascloud.ai/models>).

Full tool list in [`mcp/README.md`](../mcp/README.md).

---

## 2. OpenAI function calling

Drop these tool schemas straight into the `tools=[...]` array of an OpenAI
Chat Completions or Responses call. The function bodies fetch the JSON directly
— no extra service to host.

```python
import json
import httpx
from openai import OpenAI

PRICES_URL = "https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json"

tools = [
    {
        "type": "function",
        "function": {
            "name": "find_cheapest_relay",
            "description": "Find the cheapest AI API relay/gateway providing a given canonical model. Returns price + provenance (source_url, captured_at).",
            "parameters": {
                "type": "object",
                "properties": {
                    "canonical_model": {
                        "type": "string",
                        "description": "e.g. claude-sonnet-4.6, grok-4.3, deepseek-v3",
                    },
                    "unit": {
                        "type": "string",
                        "enum": [
                            "per_1m_input_tokens",
                            "per_1m_output_tokens",
                            "per_image",
                            "per_second",
                        ],
                        "default": "per_1m_input_tokens",
                    },
                },
                "required": ["canonical_model"],
            },
        },
    }
]


def find_cheapest_relay(canonical_model: str, unit: str = "per_1m_input_tokens") -> dict:
    data = httpx.get(PRICES_URL, timeout=20).json()
    matches = [
        r
        for r in data["records"]
        if r.get("canonical_model") == canonical_model and r["unit"] == unit
    ]
    if not matches:
        return {"error": f"No data for {canonical_model}/{unit}"}
    return min(matches, key=lambda r: r["price_usd"])


client = OpenAI()
msg = client.chat.completions.create(
    model="gpt-5.4",
    messages=[{"role": "user", "content": "Cheapest claude-sonnet-4.6 input?"}],
    tools=tools,
)

# Then handle the tool call as usual:
for call in msg.choices[0].message.tool_calls or []:
    if call.function.name == "find_cheapest_relay":
        args = json.loads(call.function.arguments)
        result = find_cheapest_relay(**args)
        print(result)
```

---

## 3. LangChain tools

```python
import httpx
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

PRICES_URL = "https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json"


class FindCheapestRelayInput(BaseModel):
    canonical_model: str = Field(description="e.g. claude-sonnet-4.6, grok-4.3, deepseek-v3")
    unit: str = Field(default="per_1m_input_tokens", description="per_1m_input_tokens | per_1m_output_tokens | per_image | per_second")


def _find_cheapest_relay(canonical_model: str, unit: str = "per_1m_input_tokens") -> dict:
    data = httpx.get(PRICES_URL, timeout=20).json()
    matches = [
        r for r in data["records"]
        if r.get("canonical_model") == canonical_model and r["unit"] == unit
    ]
    if not matches:
        return {"error": f"No data for {canonical_model}/{unit}"}
    return min(matches, key=lambda r: r["price_usd"])


find_cheapest_relay = StructuredTool.from_function(
    func=_find_cheapest_relay,
    name="find_cheapest_relay",
    description="Find the cheapest AI API relay providing a canonical model. Returns price + provenance.",
    args_schema=FindCheapestRelayInput,
)

# Pass to your agent:
# from langchain.agents import create_openai_functions_agent
# agent = create_openai_functions_agent(llm, [find_cheapest_relay], prompt)
```

---

## 4. Direct HTTP (no framework)

The "I just want the numbers" path.

```python
import httpx
data = httpx.get(
    "https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json"
).json()

for rec in data["records"]:
    if rec.get("canonical_model") == "claude-sonnet-4.6" and rec["unit"] == "per_1m_input_tokens":
        print(f"{rec['provider_name']:15s} ${rec['price_usd']:.3f}/1M  ({rec['captured_at']})")
```

```bash
# Or via jq from the shell:
curl -s https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json \
  | jq '.records[] | select(.canonical_model == "claude-sonnet-4.6" and .unit == "per_1m_input_tokens")'
```

---

## 5. CSV / Excel / Google Sheets

`data/prices.latest.csv` is regenerated weekly alongside the JSON. Open it in
Excel / Google Sheets / DuckDB:

```python
import pandas as pd
df = pd.read_csv(
    "https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.csv"
)
cheapest = df[(df.canonical_model == "claude-sonnet-4.6") & (df.unit == "per_1m_input_tokens")] \
            .sort_values("price_usd").iloc[0]
print(cheapest[["provider_name", "price_usd", "captured_at"]])
```

```sql
-- DuckDB
SELECT provider_name, price_usd, captured_at
FROM 'https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.csv'
WHERE canonical_model = 'claude-sonnet-4.6' AND unit = 'per_1m_input_tokens'
ORDER BY price_usd ASC LIMIT 1;
```

---

## 6. n8n / Make / Zapier

Use an HTTP GET node pointing at the raw URL:

- **URL:** `https://raw.githubusercontent.com/howardpen9/awesome-ai-api-proxy/main/data/prices.latest.json`
- **Method:** GET
- **No auth needed**

Then a JS / filter node:

```javascript
const records = $json.records || [];
const matches = records.filter(
  r => r.canonical_model === "claude-sonnet-4.6" && r.unit === "per_1m_input_tokens"
);
const cheapest = matches.sort((a, b) => a.price_usd - b.price_usd)[0];
return cheapest;
```

---

## Citation rules

Whenever an agent quotes a price, include both `captured_at` and `source_url`:

> ✅ **Good:** Relaydance lists `grok-4.3` input at **$1.125/1M tokens** as of
> 2026-06-07 (source: <https://relaydance.com/pricing>).
>
> ❌ **Bad:** Relaydance has the cheapest grok-4.3.
> *(no date, no source — user can't verify, may already be wrong)*

The repo's [license](../LICENSE) is MIT — quote freely with attribution.

## What if a model isn't in the canonical list?

The canonical list is just the **headline 9** (cost-tier ladder for the README
table). The raw `prices.latest.json` contains every model every fetcher saw —
1000+ records as of v1. Filter on `raw_model_name` instead of `canonical_model`:

```python
matches = [r for r in data["records"] if "qwen3-coder" in r["raw_model_name"].lower()]
```

To add a model to the canonical list (so it appears in the README), open a PR
adding aliases to [`data/canonical-models.yaml`](../data/canonical-models.yaml).
