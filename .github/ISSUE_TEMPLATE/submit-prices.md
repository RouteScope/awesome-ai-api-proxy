---
name: Submit relay prices / 提交中轉站價格
about: Submit current prices for a relay station. Operators welcome — please disclose.
title: "prices: <station name>"
labels: ["pending-price-review"]
---

<!-- English or 中文 both fine. -->

**Station name / 站點名稱:**
<!-- e.g. UiUiAPI, 云雾 API -->

**Pricing page URL / 價格頁面 URL:**
<!-- https://... -->

**Screenshot of pricing page / 價格頁面截圖:**
<!-- Drag & drop image here. REQUIRED for verification — the maintainer will cross-check
     against the live page before merging. -->

**Snapshot date / 截圖日期:** 2026-

**Prices:**

```
| canonical_model      | unit                  | price_usd |
|----------------------|-----------------------|-----------|
| claude-sonnet-4.6    | per_1m_input_tokens   | 1.50      |
| claude-sonnet-4.6    | per_1m_output_tokens  | 7.50      |
| grok-4.3             | per_1m_input_tokens   | 1.20      |
| deepseek-v3          | per_1m_input_tokens   | 0.20      |
```

> Use the canonical model names from
> [`data/canonical-models.yaml`](../../blob/main/data/canonical-models.yaml).
> Valid units: `per_1m_input_tokens`, `per_1m_output_tokens`,
> `per_1m_input_cache_read_tokens`, `per_image`, `per_second`, `per_request`.

**Are you the station operator? / 你是站點營運者嗎？:** yes / no

---
- [ ] Screenshot included / 已附截圖
- [ ] Prices match the live page on the snapshot date / 價格與當天頁面一致
- [ ] No referral / affiliate links in the URL / URL 無推廣連結
- [ ] If operator: I'm disclosing this submission as self-promotion / 若為營運者，已揭露
