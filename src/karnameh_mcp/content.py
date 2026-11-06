"""Karnameh car encyclopedia (specs, reviews, comparison), the car blog, inspection centers and market statistics."""

from __future__ import annotations

import asyncio
import html
import re
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, fetch
from .karnameh import PRICES, kn_cars
from .registry import tool

AUTODETAIL = "/autodetail/api/v1/brand-model"
BLOG = f"{SITE}/blog/wp-json/wp/v2"
Slug = Annotated[
    str,
    Field(
        description="Variant `slug` from kn_specs_search.",
        pattern=r"^[a-z0-9][a-z0-9._-]{1,100}$",
    ),
]


def _text(h: str) -> str:
    """HTML from the WordPress API as plain text."""
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    h = re.sub(r"(?i)</(p|h\d|li|div)>|<br\s*/?>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", "", h)).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", h)).strip()


@tool("Search car variants with specs")
async def kn_specs_search(
    query: Annotated[
        str,
        Field(description="Brand, model or variant, Persian or English, e.g. corolla.", min_length=1),
    ],
    limit: Annotated[int, Field(description="Matches to return.", ge=1, le=30)] = 10,
) -> dict[str, Any]:
    """Find car variants in Karnameh's specs catalog and return the `slug` that kn_specs and kn_compare_specs take.

    Only results with `variant: true` have specs; otherwise search again with more words.
    """
    rows = await fetch(f"{AUTODETAIL}/search/", {"q": query.strip()})
    out = [
        {
            "slug": r["slug"],
            "name": r["full_title"],
            "variant": bool(r.get("is_last_level")),
            "level": r.get("model_type"),
            "brand_en": r.get("en_brand"),
            "country": (r.get("manufacture_country") or {}).get("fa_name"),
        }
        for r in rows
    ]
    out.sort(key=lambda r: not r["variant"])
    return {"matched": len(out), "cars": out[:limit]}


def _rows(items: list[dict[str, Any]]) -> dict[str, str]:
    return {
        r["key"]["text"]: r["value"]["text"]
        for r in items
        if r.get("widget_type") == "TABLE_ROW" and r["value"]["text"] != "-"
    }


def _parse_widgets(widgets: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten Karnameh's server-driven widget tree (title, images, review box, spec tables, web reviews)."""
    out: dict[str, Any] = {}
    for w in widgets:
        kind, key = w.get("widget_type"), w.get("key")
        if kind == "TITLE_ROW":
            out["title"] = w.get("text")
        elif key == "general_images":
            out["images"] = [i["url"] for i in w.get("items", []) if i.get("url")][:5]
        elif key == "review":
            for it in w["items"]:
                t = it.get("widget_type")
                if t == "REVIEW_ROW":
                    score = ((it.get("description") or {}).get("score") or {}).get("value")
                    out["score_out_of_10"] = score if isinstance(score, int | float) else None  # "-" when unrated
                elif t == "REVIEW_BOX":
                    pros, cons = [], []
                    for r in it["items"]:
                        if r["widget_type"] == "AI_GENERATED_ROW":
                            out["review_summary"] = r["text"]
                        elif r["widget_type"] == "DETAIL_ROW":
                            (cons if "negative" in (r.get("icon") or {}).get("url", "") else pros).append(r["text"])
                    out["pros"], out["cons"] = pros, cons
        elif key == "tech_specs":
            sections: dict[str, dict[str, str]] = {}
            for it in w["items"]:
                if it["widget_type"] == "CELL_ROW":
                    out["highlights"] = {
                        c["key"]["text"]: c["value"]["text"] for c in it["cells"] if c["value"]["text"] != "-"
                    }
                elif it["widget_type"] == "EXPANDABLE_ROW":
                    sections[it["text"]] = _rows(it["items"])
            out["specs"] = sections
        elif key == "contents":
            reviews: list[dict[str, Any]] = []
            for box in w["items"]:
                if box.get("widget_type") != "CONTENT_BOX":
                    continue
                for it in box["items"]:
                    if it["widget_type"] == "CONTENT_ROW":
                        reviews.append(
                            {
                                "source": it["title"]["text"],
                                "age": (it.get("subtitle") or {}).get("text"),
                                "score_out_of_10": ((it.get("description") or {}).get("score") or {}).get("value"),
                            }
                        )
                    elif reviews and it["widget_type"] == "SUBTITLE_ROW":
                        reviews[-1]["text"] = it["text"][:500]
                    elif reviews and it["widget_type"] == "BUTTON_BOX":
                        reviews[-1]["url"] = it.get("url")
            out["web_reviews"] = reviews
    return out


async def _variant(slug: str) -> dict[str, Any]:
    fallback = None
    try:
        body = await fetch(f"{AUTODETAIL}/info/{slug}")
    except ApiError as e:
        if e.status != 400:
            raise
        # a catalog variant with no spec sheet of its own: `info` answers 400, so use its parent model's sheet
        detail = await fetch(f"{AUTODETAIL}/brand-model-detail/{slug}/", {"lookup_field": "slug"})
        fallback = ((detail.get("parent_detail") or {}).get("parent") or {}).get("slug")
        if not fallback:
            raise
        body = await fetch(f"{AUTODETAIL}/info/{fallback}")
    types = body.get("types") or []
    if not types:
        raise ApiError("No specs for that slug. Find a variant slug with kn_specs_search.")
    if len(types) > 1:
        names = ", ".join(t["slug"] for t in types[:8])
        raise ApiError(f"That slug is a model with several variants. Pick one of: {names}.")
    crumbs = body.get("breadcrumb", [])
    path = "/".join([crumbs[0]["slug"], *(b["en_title"] for b in crumbs[1:])]) if crumbs else ""
    note = {"note": f"No spec sheet for {slug}; showing its model {fallback}."} if fallback else {}
    return {
        "slug": types[0]["slug"],
        **note,
        **_parse_widgets(types[0]["widgets"]),
        "url": f"{SITE}/car-reviews/{path}",
    }


@tool("Car specs and review summary")
async def kn_specs(slug: Slug) -> dict[str, Any]:
    """Get one car variant's technical specs, Karnameh's expert review score, pros and cons and web reviews.

    Use after kn_specs_search. The summary and score are AI-written from web reviews: opinion.
    """
    return await _variant(slug)


@tool("Compare car specs")
async def kn_compare_specs(
    slugs: Annotated[list[Slug], Field(description="Variant slugs from kn_specs_search.", min_length=2, max_length=4)],
    only_differences: Annotated[bool, Field(description="Only rows where the cars differ.")] = True,
) -> dict[str, Any]:
    """Compare two to four car variants side by side: review score, pros, cons and every spec row.

    Use for "A or B?" after kn_specs_search. Spec values follow the order of `cars`.
    """
    cars = [await _variant(s) for s in slugs]
    rows: dict[str, dict[str, list[str | None]]] = {}
    for sec in dict.fromkeys(k for c in cars for k in c.get("specs", {})):
        for key in dict.fromkeys(k for c in cars for k in c.get("specs", {}).get(sec, {})):
            vals = [c.get("specs", {}).get(sec, {}).get(key) for c in cars]
            if not only_differences or len(set(vals)) > 1:
                rows.setdefault(sec, {})[key] = vals
    return {
        "cars": [
            {k: c.get(k) for k in ("slug", "title", "score_out_of_10", "pros", "cons", "highlights")} for c in cars
        ],
        "specs": rows,
    }


@tool("Car blog articles")
async def kn_articles(
    query: Annotated[str | None, Field(description="Persian search words.")] = None,
    category: Annotated[
        Literal[
            "car-news",
            "car-reviews",
            "car-maintenance",
            "car-learning",
            "car-rules",
            "legal-tips",
            "periodic-maintenance-service",
            "introduction",
        ]
        | None,
        Field(description="Blog section."),
    ] = None,
    limit: Annotated[int, Field(description="Articles to return.", ge=1, le=20)] = 10,
    page: Annotated[int, Field(description="Page number.", ge=1)] = 1,
) -> dict[str, Any]:
    """Search or list articles of the Karnameh car magazine: news, reviews, maintenance, laws.

    Newest first. Read one with kn_article(id).
    """
    params: dict[str, Any] = {
        "per_page": limit,
        "page": page,
        "search": query,
        "_fields": "id,date,link,title,excerpt,categories",
    }
    if category:
        cats = await fetch(f"{BLOG}/categories", {"slug": category, "_fields": "id"})
        if not cats:
            raise ApiError("Unknown blog category.")
        params["categories"] = cats[0]["id"]
    try:
        posts = await fetch(f"{BLOG}/posts", params)
    except ApiError as e:
        if e.status == 400:  # WordPress answers 400 for a page past the end
            return {"page": page, "count": 0, "articles": []}
        raise
    return {
        "page": page,
        "count": len(posts),
        "articles": [
            {
                "id": p["id"],
                "title": _text(p["title"]["rendered"]),
                "date": p["date"][:10],
                "summary": _text(p["excerpt"]["rendered"])[:300],
                "url": p["link"],
            }
            for p in posts
        ],
    }


@tool("Read a blog article")
async def kn_article(
    id: Annotated[int, Field(description="Article id from kn_articles.", ge=1)],
    max_chars: Annotated[int, Field(description="Cut text after this many characters.", ge=500, le=20000)] = 6000,
) -> dict[str, Any]:
    """Read one article of the Karnameh car magazine as plain text.

    Use after kn_articles. Cut at `max_chars` (`truncated`); `url` has the full page.
    """
    p = await fetch(f"{BLOG}/posts/{id}", {"_fields": "id,date,modified,link,title,content"})
    body = _text(p["content"]["rendered"])
    return {
        "id": p["id"],
        "title": _text(p["title"]["rendered"]),
        "date": p["date"][:10],
        "modified": p["modified"][:10],
        "text": body[:max_chars],
        "truncated": len(body) > max_chars,
        "url": p["link"],
    }


@tool("Biggest new-car price movers")
async def kn_price_movers(
    direction: Annotated[Literal["up", "down", "any"], Field(description="Biggest rises, drops, or either.")] = "up",
    days: Annotated[int, Field(description="Only quotes within this many days of the newest.", ge=1, le=30)] = 3,
    year: Annotated[int | None, Field(description="Production year (Persian, 1404).", ge=1380, le=1450)] = None,
    limit: Annotated[int, Field(description="Rows to return.", ge=1, le=50)] = 15,
) -> dict[str, Any]:
    """Rank new (zero-km) car variants by the percent change of their latest price quote.

    `change_percent` is against the previous quote. Trend: kn_price_history with a row's `name`.
    """
    rows = await fetch(f"{PRICES}/last-prices/")
    newest = max(r["date"] for r in rows)
    cutoff = (date.fromisoformat(newest) - timedelta(days=days - 1)).isoformat()
    rows = list(
        {
            (r["brand_model"], r["year"]): r
            for r in sorted(
                rows, key=lambda r: (r["date"], abs(r["change"] or 0))
            )  # upstream repeats rows, some with 0
            if (not year or r["year"] == year) and r["date"] >= cutoff and r.get("change") is not None
        }.values()
    )
    key = {"up": lambda r: -r["change"], "down": lambda r: r["change"], "any": lambda r: -abs(r["change"])}[direction]
    rows.sort(key=key)
    return {
        "newest_quote": newest,
        "matched": len(rows),
        "movers": [
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


@tool("Used-car listing counts per city")
async def kn_city_stats(
    brand: Annotated[str | None, Field(description="English or Persian brand (kn_brands).")] = None,
    model: Annotated[str | None, Field(description="Model within the brand.")] = None,
    max_price: Annotated[int | None, Field(description="Maximum price, Toman.", ge=0)] = None,
) -> dict[str, Any]:
    """Count Karnameh's used-car ads in every city, optionally for one brand, model or price ceiling.

    Gives each city's cheapest ad. Makes one request per city, so it is slower than kn_cars(city=...).
    """
    cities = (await fetch("/rest/api/cities/v1/"))["data"]
    results = await asyncio.gather(
        *(
            kn_cars(brand=brand, model=model, city=c["en_name"], max_price=max_price, sort="cheapest", limit=1)
            for c in cities
        )
    )
    out = []
    for c, r in zip(cities, results, strict=True):
        cheapest = r["ads"][0] if r["ads"] else None
        out.append(
            {
                "city": c["en_name"],
                "name": c["name"],
                "ads": r["total"],
                "cheapest": cheapest and {k: cheapest[k] for k in ("id", "title", "price_toman")},
            }
        )
    out.sort(key=lambda c: -c["ads"])
    return {"total": sum(c["ads"] for c in out), "cities": out}


@tool("Karnameh inspection centers")
async def kn_inspection_centers(
    city_id: Annotated[int, Field(description="City `id` from kn_cities.", ge=1)],
) -> dict[str, Any]:
    """List Karnameh's walk-in car inspection and paint-check centers in a city, with address and map coordinates.

    Booking and prices are not available here.
    """
    rows = await fetch("/rest/api/evaluation/v1/inspection-center/", {"city_id": city_id})
    return {
        "count": len(rows),
        "centers": [
            {
                "name": r["title"],
                "address": r["address"],
                "lat": float(r["geometry"]["coordinates"][1]),
                "lon": float(r["geometry"]["coordinates"][0]),
                "url": f"{SITE}/car-inspection",
            }
            for r in rows
        ],
    }
