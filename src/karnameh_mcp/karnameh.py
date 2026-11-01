"""Karnameh tools: used-car ads, ad details, brands and cities, zero-km market prices and price history."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, fetch
from .registry import tool

STORAGE = "/post-storage/car-posts"
PRICES = "/priceestimator/api/zeroprice"

AdId = Annotated[
    str,
    Field(
        description="Ad id (the `id` field from kn_cars), a UUID like 4385b37e-6ce5-413b-9477-6386b20902bd.",
        pattern=r"^[0-9a-fA-F-]{36}$",
    ),
]
PriceName = Annotated[
    str,
    Field(
        description="Exact English model-variant name from kn_price_list (`name`), e.g. 'Peugeot 207i Manual TU5P'.",
        min_length=3,
        max_length=100,
    ),
]
SORTS = {"newest": "newest", "cheapest": "price-ascending", "priciest": "price-descending"}


def _gregorian(year: int | None) -> int | None:
    """The ads filter works in Gregorian years; accept Persian years (1300-1500) too."""
    return year + 621 if year and year < 1700 else year


def _ad(p: dict[str, Any]) -> dict[str, Any]:
    """One ad card from the list API, trimmed."""
    return {
        "id": p["concierge_sale_token"],
        "title": p["title"],
        "brand": p.get("brand_name_fa"),
        "model": p.get("model_name_fa"),
        "type": p.get("type_name_fa"),
        "brand_en": p.get("brand_name_en"),
        "model_en": p.get("model_name_en"),
        "year": p["year"],
        "usage_km": p["usage"],
        "price_toman": p["price"],
        "city": p["city_name_fa"],
        "gearbox": p.get("gearbox_name_fa"),
        "inspected": p["has_inspection"],
        "installments": p["is_leasing_available"],
        "min_prepayment_toman": round(p["prepayment_amount"]) if p.get("prepayment_amount") else None,
        "photos": p.get("image_count"),
        "image": p.get("image"),
        "url": f"{SITE}/used-cars/{p['concierge_sale_token']}",
    }


_catalog: list[dict[str, str]] | None = None


async def _catalog_rows() -> list[dict[str, str]]:
    """Karnameh's brand/model/type catalog (about 1400 rows), fetched once per process."""
    global _catalog
    if _catalog is None:
        body = await fetch(
            "/rest/api/find_cars/v1/brand_models", {"service_name": "inspection", "vehicle_type": "light_car"}
        )
        _catalog = body["data"]
    return _catalog


async def _english(brand: str | None, model: str | None) -> tuple[str | None, str | None]:
    """Turn Persian brand/model names into the English ones the ads filter wants; English passes through."""
    if not (brand and not brand.isascii()) and not (model and not model.isascii()):
        return brand, model
    rows = await _catalog_rows()
    if brand and not brand.isascii():
        brand = next((r["brand_en"] for r in rows if r["brand_fa"] == brand.strip()), None)
        if brand is None:
            raise ApiError("Unknown brand name. Look it up with kn_brands.")
    if model and not model.isascii():
        model = next(
            (
                r["model_en"]
                for r in rows
                if r["model_fa"] == model.strip() and (not brand or r["brand_en"].lower() == brand.lower())
            ),
            None,
        )
        if model is None:
            raise ApiError("Unknown model name. Look it up with kn_brands.")
    return brand, model


@tool("Search used-car ads")
async def kn_cars(
    query: Annotated[
        str | None,
        Field(description="Free text in Persian, e.g. 'سمند' or 'پژو 206'. Use brand/model for exact filters."),
    ] = None,
    brand: Annotated[
        str | None,
        Field(description="Brand name, English slug (peugeot, kia, toyota) or Persian (پژو). See kn_brands."),
    ] = None,
    model: Annotated[
        str | None,
        Field(
            description="Model name within the brand, e.g. 206 or Corolla (English as listed by kn_brands) or Persian."
        ),
    ] = None,
    city: Annotated[str | None, Field(description="City slug from kn_cities, e.g. tehran, karaj, mashhad.")] = None,
    min_price: Annotated[
        int | None, Field(description="Minimum price in Toman, e.g. 1000000000 for one billion.", ge=0)
    ] = None,
    max_price: Annotated[int | None, Field(description="Maximum price in Toman.", ge=0)] = None,
    min_year: Annotated[
        int | None, Field(description="Oldest model year, Persian (1398) or Gregorian (2019).", ge=1300, le=2100)
    ] = None,
    max_year: Annotated[
        int | None, Field(description="Newest model year, Persian or Gregorian.", ge=1300, le=2100)
    ] = None,
    max_usage_km: Annotated[int | None, Field(description="Maximum odometer reading in km.", ge=0)] = None,
    inspected_only: Annotated[bool, Field(description="Only ads with a Karnameh expert inspection report.")] = False,
    installments_only: Annotated[bool, Field(description="Only ads that can be bought in instalments.")] = False,
    sort: Annotated[Literal["newest", "cheapest", "priciest"], Field(description="Result order.")] = "newest",
    limit: Annotated[int, Field(description="How many ads to return (1-50).", ge=1, le=50)] = 20,
    offset: Annotated[int, Field(description="Skip this many ads (paging).", ge=0)] = 0,
) -> dict[str, Any]:
    """Search Karnameh's used-car ads (karnameh.com/buy-used-cars) by brand, model, city, price, year and mileage.

    Use this to find cars for sale or to see what a model costs on the market. Prices are asking prices in Toman.
    Pass an ad's `id` to kn_car for the full description, strengths and inspection summary. Only Karnameh's own
    listed ads are covered (a few hundred), not all of Iran.
    """
    brand, model = await _english(brand, model)
    body = await fetch(
        f"{STORAGE}/car-post-list/",
        {
            "search_query": query,
            "brand_models": brand,
            "models": model,
            "city_slugs": city,
            "min_price": min_price,
            "max_price": max_price,
            "min_year": _gregorian(min_year),
            "max_year": _gregorian(max_year),
            "max_usage": max_usage_km,
            "should_attach_inspection_report": "true" if inspected_only else None,
            "is_leasing_available": "true" if installments_only else None,
            "sort": SORTS[sort],
            "size": limit,
            "start": offset,
        },
    )
    ads = [_ad(p) for p in body["car_posts"]]
    return {"total": body["total"], "offset": offset, "count": len(ads), "ads": ads}


@tool("Get one used-car ad")
async def kn_car(id: AdId) -> dict[str, Any]:
    """Get one Karnameh used-car ad: price, specs, seller's description, strengths and the inspection summary.

    Use after kn_cars to read an ad in full. The detailed inspection report itself needs a Karnameh login, so only
    its date, link and one-line body verdict are returned. Seller phone numbers are not available.
    """
    d = await fetch(f"{STORAGE}/car-post-detail/{id}/")
    try:
        summary = await fetch(f"{STORAGE}/car-post-detail/{id}/summary/")
    except ApiError:
        summary = {}
    strengths = [s["label"] for group in (d.get("strengths") or {}).values() for s in group]
    info = summary.get("carmaa_info") or {}
    desc = (d.get("description") or "").strip()
    return {
        "id": d["token"],
        "title": d["title"],
        "brand": d.get("brand_name_fa"),
        "model": d.get("model_name_fa"),
        "type": d.get("type_name_fa"),
        "year": d.get("displayable_year"),
        "usage_km": d["usage"],
        "price_toman": d["advertisement_price"],
        "min_prepayment_toman": d.get("prepayment_amount"),
        "installments": d["is_leasing_available"],
        "city": d["city_name_fa"],
        "body_status": d.get("body_status"),
        "specs": {w["name"]: w["value"] for w in d.get("widget") or []},
        "strengths": strengths,
        "description": desc[:1500],
        "inspection": {
            "date": (d.get("inspection_date") or "")[:10] or None,
            "report_link": d.get("inspection_report_link"),
            "verdict": info.get("carmaa_info"),
            "status": info.get("carmaa_status"),
        }
        if d["has_inspection"]
        else None,
        "updated": (d.get("price_update_date") or "")[:10],
        "photos": [c["url"] for c in d.get("car_images") or []][:8],
        "url": f"{SITE}/used-cars/{d['token']}",
    }


@tool("Look up car brands and models")
async def kn_brands(
    query: Annotated[
        str | None,
        Field(
            description="Part of a brand or model name, Persian or English, e.g. پژو, 206, kia. Empty lists all brands."
        ),
    ] = None,
) -> dict[str, Any]:
    """Look up Karnameh's car brands and models, Persian and English, to get the names the other tools expect.

    Use first when you only have a Persian name or are unsure of the spelling. Pass the English `brand` and `model`
    values to kn_cars. Zero-km price lists (kn_price_list) use their own English variant names.
    """
    rows = await _catalog_rows()
    q = (query or "").strip().lower()
    brands: dict[str, dict[str, Any]] = {}
    for r in rows:
        hay = f"{r['name_en']} {r['name_fa']}".lower()
        if q and q not in hay:
            continue
        b = brands.setdefault(r["brand_en"], {"brand_en": r["brand_en"], "brand_fa": r["brand_fa"], "models": {}})
        b["models"][r["model_en"]] = r["model_fa"]
    out = list(brands.values())
    if q:
        return {
            "count": len(out),
            "brands": [{**b, "models": [{"en": k, "fa": v} for k, v in b["models"].items()]} for b in out[:20]],
        }
    return {
        "count": len(out),
        "brands": [{"brand_en": b["brand_en"], "brand_fa": b["brand_fa"], "models": len(b["models"])} for b in out],
    }


@tool("List cities")
async def kn_cities() -> dict[str, Any]:
    """List the cities Karnameh serves, with the slug kn_cars takes as `city` and the id kn_inspection_centers takes."""
    body = await fetch("/rest/api/cities/v1/")
    return {"cities": [{"id": c["pk"], "slug": c["en_name"], "name": c["name"]} for c in body["data"]]}


def _price_item(i: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": i["name_en"],
        "name_fa": i["name_fa"],
        "year": i["production_year"],
        "option": i.get("option"),
        "market_price": i.get("market_price"),
        "dealership_price": i.get("dealership_price"),
        "factory_price": i.get("factory_price"),
        "sources": [s["source_fa"] for s in i.get("sources", [])],
    }


@tool("New-car market prices")
async def kn_price_list(
    brand: Annotated[
        str | None, Field(description="English brand name as in the price list, e.g. Peugeot, Toyota, Changan.")
    ] = None,
    model: Annotated[str | None, Field(description="English model name within the brand, e.g. 207i.")] = None,
    search: Annotated[str | None, Field(description="Free text in Persian, e.g. سمند.")] = None,
    origin: Annotated[
        Literal["domestic", "foreign"] | None, Field(description="Iranian-made or imported cars.")
    ] = None,
    country: Annotated[
        str | None,
        Field(description="Country of manufacture in English: China, Iran, Japan, Korea, German, France or Italia."),
    ] = None,
    min_price: Annotated[int | None, Field(description="Minimum market price, Toman.", ge=0)] = None,
    max_price: Annotated[int | None, Field(description="Maximum market price, Toman.", ge=0)] = None,
    year: Annotated[
        int | None, Field(description="Only this production year (Persian, e.g. 1405).", ge=1380, le=1450)
    ] = None,
    page: Annotated[int, Field(description="Page of 10 model groups; the answer says how many pages exist.", ge=1)] = 1,
) -> dict[str, Any]:
    """List today's market prices of new (zero-km) cars from Karnameh's car-price pages (karnameh.com/car-price).

    Use for "how much is a new X" or to compare models. Prices are Toman and daily; each row is a variant and
    production year with its price sources. Only variants Karnameh prices today are listed (no Peugeot Pars or 405;
    kn_latest_prices has older ones). For price movement over time call kn_price_history with a row's `name`.
    """
    body = await fetch(
        f"{PRICES}/prices/list/",
        {
            "brand_en": brand,
            "model_en": model,
            "search": search,
            "origin": origin,
            "country": country,
            "min_price": min_price,
            "max_price": max_price,
            "page": page if page > 1 else None,
        },
    )
    groups = []
    for g in body["results"]:
        items = [_price_item(i) for i in g["items"] if not year or i["production_year"] == year]
        if items:
            info = g["brand_model_info"]
            groups.append(
                {
                    "brand": g["brand_fa"],
                    "brand_en": g["brand_en"],
                    "maker": info.get("manufacture_factory_fa_name"),
                    "country": info.get("manufacture_country_fa_name"),
                    "updated": g["last_modified_at"][:10],
                    "prices": items,
                }
            )
    return {"groups_total": body["count"], "page": page, "has_next_page": bool(body["next"]), "groups": groups}


@tool("Latest new-car price quotes")
async def kn_latest_prices(
    query: Annotated[
        str | None, Field(description="Part of the English variant name, e.g. Pars, Dena, Corolla. Empty for all.")
    ] = None,
    year: Annotated[int | None, Field(description="Production year (Persian, e.g. 1404).", ge=1380, le=1450)] = None,
    limit: Annotated[int, Field(description="How many quotes to return (1-100).", ge=1, le=100)] = 25,
) -> dict[str, Any]:
    """List the most recent price quotes of new cars with the day's percent change.

    Covers more variants than kn_price_list (including older models), each with the date of its last quote.
    Use to see what moved lately or to find a variant's exact English name for kn_price_history.
    """
    rows = await fetch(f"{PRICES}/last-prices/")
    q = (query or "").strip().lower()
    rows = [r for r in rows if (not q or q in r["brand_model"].lower()) and (not year or r["year"] == year)]
    rows = list(
        {(r["brand_model"], r["year"], r["date"], r["price"]): r for r in rows}.values()
    )  # upstream repeats rows
    rows.sort(key=lambda r: (r["date"], r["brand_model"]), reverse=True)
    return {
        "matched": len(rows),
        "quotes": [
            {
                "name": r["brand_model"],
                "year": r["year"],
                "price_toman": r["price"],
                "change_percent": r["change"],
                "date": r["date"],
            }
            for r in rows[:limit]
        ],
    }


@tool("New-car price history")
async def kn_price_history(
    name: PriceName,
    year: Annotated[
        int | None, Field(description="Production year (Persian). Omit for every year.", ge=1380, le=1450)
    ] = None,
    days: Annotated[
        int, Field(description="How many of the latest daily points to return per year (1-90).", ge=1, le=90)
    ] = 30,
) -> dict[str, Any]:
    """Get the daily average market price history of one new-car variant, per production year.

    Use after kn_price_list or kn_latest_prices for a trend ("is it going up?"). `name` must be the exact English
    variant name. With `year`, also lists each source's current quote for that year.
    """
    body = await fetch(f"{PRICES}/prices/averages/daily/", {"brand_model": name})
    years = {}
    for y, v in body["years"].items():
        if year and str(year) != y:
            continue
        rng = v["range"]
        series = {}
        for opt, o in v["items"].items():
            pts = [
                {"day": p["day"], "price": int(p["avg_market_price"])} for p in o["items"] if p.get("avg_market_price")
            ]
            series[opt] = pts[-days:]
        years[y] = {
            "min_price": int(rng["min_avg_market_price"]) if rng.get("min_avg_market_price") else None,
            "max_price": int(rng["max_avg_market_price"]) if rng.get("max_avg_market_price") else None,
            "daily": series,
        }
    if not years:
        raise ApiError(
            "No price history for that name. Use the exact English `name` from kn_price_list or kn_latest_prices."
        )
    out: dict[str, Any] = {"name": name, "years": years}
    if year:
        det = await fetch(f"{PRICES}/prices/detail/", {"slug": name, "year": year, "price_source": "M"})
        out["sources"] = [
            {"source": d["source_fa"], "price": d["price"], "change_percent": d["change"], "date": d["date"]}
            for d in det
        ]
    return out
