<!-- mcp-name: io.github.sepehr071/karnameh-mcp -->

<div align="center">

# karnameh-mcp: Karnameh (کارنامه) used-car ads and car prices MCP server for AI agents

**karnameh-mcp is an unofficial, read-only MCP server that gives AI agents the public data of Karnameh (karnameh.com), an Iranian car marketplace.**<br>
Its 15 tools search used-car ads with real filters, read an ad in full, look up brands and cities, list today's market prices of new cars with history and biggest movers, give car specs and expert review summaries with side-by-side comparison, count ads per city, and read the Karnameh car magazine.<br>
No API key or Karnameh account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[![PyPI](https://img.shields.io/pypi/v/karnameh-mcp?color=2563eb)](https://pypi.org/project/karnameh-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/karnameh-mcp)](https://pypi.org/project/karnameh-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/karnameh-mcp/blob/main/LICENSE)

[For AI agents](#for-ai-agents) · [Quick start](#quick-start) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

</div>

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for karnameh.com: used-car ads with filters (brand, model, city, price, year, mileage, inspected, instalments), full ad details, brand and city lookup, zero-km market prices and daily price history.
- **Install:** `uvx karnameh-mcp` or `claude mcp add karnameh -- uvx karnameh-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account. Optional `KARNAMEH_MCP_PROXY` (HTTP proxy URL, or a comma-separated list); system proxy settings are ignored.
- **Access:** read-only. It cannot log in, contact sellers, book inspections or post ads, so no confirmation is needed before calling any tool.
- **Tools:** 15, all prefixed `kn_`. Typical sequences: `kn_cars` -> `kn_car`; `kn_price_list` -> `kn_price_history`; `kn_brands` -> `kn_cars`; `kn_specs_search` -> `kn_specs` / `kn_compare_specs`; `kn_articles` -> `kn_article`.
- **Use when:** the user asks what a used car costs in Iran, wants to find a car for sale by brand, model, budget or city, wants one ad read in full, or asks the price of a new (zero-km) car and how it moved lately.
- **Do not use when:** the user needs the full Karnameh inspection report, a price estimate for their own car (both need a Karnameh login) or ads from other sites.
- **Output:** compact JSON. Prices are Toman. Names and descriptions are Persian, as Karnameh has them.
- **Machine-readable:** [`server.json`](https://github.com/sepehr071/karnameh-mcp/blob/main/server.json) and the
  [iran-mcp catalog](https://github.com/sepehr071/iran-mcp).

## Quick start

```bash
claude mcp add karnameh -- uvx karnameh-mcp
```

Any other client: command `uvx`, args `["karnameh-mcp"]`.

## Tools

| Tool | What it does |
| --- | --- |
| `kn_cars` | Search used-car ads by text, brand, model, city, price, year, mileage, inspected, instalments; sort; page. |
| `kn_car` | One ad in full: specs, description, strengths, inspection date, link and verdict. |
| `kn_brands` | Brand and model names in Persian and English. |
| `kn_cities` | City slugs for `kn_cars`. |
| `kn_price_list` | Today's market prices of new cars by brand, model, origin, country, price, year. |
| `kn_latest_prices` | Most recent price quotes with percent change. |
| `kn_price_history` | Daily average price per production year, plus each source's quote for a year. |
| `kn_price_movers` | New-car variants ranked by their latest percent price change (rises, drops). |
| `kn_specs_search` | Find a car variant's slug in the specs catalog. |
| `kn_specs` | Technical specs, AI review score, pros and cons, web reviews of one variant (falls back to the parent model's sheet, with a note, when the variant has none). |
| `kn_compare_specs` | Two to four variants side by side (only the differing rows by default). |
| `kn_city_stats` | Used-ad count and cheapest ad in every city, optionally per brand or model. |
| `kn_inspection_centers` | Karnameh walk-in inspection and paint-check centers of a city. |
| `kn_articles` | Search or list the Karnameh car magazine (news, reviews, maintenance, laws). |
| `kn_article` | One magazine article as plain text. |

## FAQ

**Does it need a Karnameh account?** No. Everything is public data the website shows to anyone.

**How many ads are there?** Karnameh lists a few hundred used cars at a time, so this is not the whole Iranian market.

**Why is there no price estimator or inspection report?** Both need a Karnameh login on the website.

**Proxy?** The server ignores system proxies. Set `KARNAMEH_MCP_PROXY` if you need one.

## فارسی

سرور MCP غیررسمی و فقط‌خواندنی برای کارنامه (karnameh.com): جستجوی آگهی خودروی کارکرده با فیلتر برند، مدل، شهر، قیمت، سال و کارکرد، خواندن کامل یک آگهی، قیمت روز خودروی صفر و روند قیمت. بدون کلید API و بدون حساب کاربری.

نصب: `claude mcp add karnameh -- uvx karnameh-mcp`

ساخته‌شده توسط سپهر رادمرد: github.com/sepehr071 · linkedin.com/in/sepehr-radmard
