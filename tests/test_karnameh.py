import pytest
from conftest import fixture

from karnameh_mcp import karnameh

pytestmark = pytest.mark.anyio

AD = "baaf71a3-3544-47ea-8335-084e318ad263"
LIST = "/post-storage/car-posts/car-post-list/"
TOOLS = {
    "kn_cars",
    "kn_car",
    "kn_brands",
    "kn_cities",
    "kn_price_list",
    "kn_latest_prices",
    "kn_price_history",
    "kn_specs_search",
    "kn_specs",
    "kn_compare_specs",
    "kn_articles",
    "kn_article",
    "kn_price_movers",
    "kn_city_stats",
    "kn_inspection_centers",
}


@pytest.fixture(autouse=True)
def reset_catalog():
    karnameh._catalog = None


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.title and t.description.splitlines()[0].endswith("."), t.name
        assert "title" not in str(t.input_schema.get("properties", {}).values()), t.name


async def test_cars_maps_filters_and_trims_ads(client, api):
    api[LIST] = fixture("ads.json")
    r = (
        await client.call_tool(
            "kn_cars",
            {
                "brand": "peugeot",
                "model": "206",
                "city": "tehran",
                "min_year": 1398,
                "max_price": 2000000000,
                "sort": "cheapest",
                "limit": 3,
            },
        )
    ).structured_content
    q = api.calls[0].url.params
    assert q["brand_models"] == "peugeot" and q["models"] == "206" and q["city_slugs"] == "tehran"
    assert q["min_year"] == "2019" and q["max_price"] == "2000000000"  # Persian year -> Gregorian
    assert q["sort"] == "price-ascending" and q["size"] == "3" and q["start"] == "0"
    assert "min_price" not in q and "search_query" not in q
    assert r["total"] == 7 and r["count"] == 3
    ad = r["ads"][0]
    assert ad["id"] and ad["url"].endswith("/used-cars/" + ad["id"]) and isinstance(ad["price_toman"], int)
    assert "images" not in ad and "car_images" not in ad


async def test_cars_gregorian_year_passes_through(client, api):
    api[LIST] = fixture("ads.json")
    await client.call_tool("kn_cars", {"max_year": 2024, "inspected_only": True})
    q = api.calls[0].url.params
    assert q["max_year"] == "2024" and q["should_attach_inspection_report"] == "true"


async def test_cars_persian_brand_is_resolved_through_catalog(client, api):
    api["/rest/api/find_cars/v1/brand_models"] = fixture("catalog.json")
    api[LIST] = fixture("ads.json")
    await client.call_tool("kn_cars", {"brand": "پژو", "model": "206"})
    assert api.calls[0].url.path.endswith("brand_models")
    assert api.calls[1].url.params["brand_models"] == "Peugeot"


async def test_cars_unknown_persian_brand_is_an_error(client, api):
    api["/rest/api/find_cars/v1/brand_models"] = fixture("catalog.json")
    r = await client.call_tool("kn_cars", {"brand": "نامعلوم"})
    assert r.is_error


async def test_car_detail_with_inspection_summary(client, api):
    api[f"/post-storage/car-posts/car-post-detail/{AD}/"] = fixture("detail.json")
    api[f"/post-storage/car-posts/car-post-detail/{AD}/summary/"] = fixture("summary.json")
    r = (await client.call_tool("kn_car", {"id": AD})).structured_content
    assert r["id"] == AD and r["price_toman"] == 8450000000 and r["year"] == 2024 and r["usage_km"] == 3000
    assert r["specs"]["شهر"] and r["strengths"]
    assert r["inspection"]["report_link"].startswith("https://karnameh.com/car-inspection/report/")
    assert r["inspection"]["verdict"] and r["inspection"]["date"] == "2026-02-21"
    assert len(r["photos"]) <= 8


async def test_car_rejects_bad_id(client, api):
    try:
        r = await client.call_tool("kn_car", {"id": "../etc"})
        assert r.is_error
    except Exception:  # noqa: BLE001  (the SDK may raise validation errors)
        pass
    assert not api.calls


async def test_car_upstream_404_is_a_tool_error(client, api):
    r = await client.call_tool("kn_car", {"id": AD})
    assert r.is_error and "404" in r.content[0].text


async def test_brands_search_and_listing(client, api):
    api["/rest/api/find_cars/v1/brand_models"] = fixture("catalog.json")
    found = (await client.call_tool("kn_brands", {"query": "206"})).structured_content
    assert found["count"] == 1 and found["brands"][0]["brand_en"] == "Peugeot"
    assert {"en": "206", "fa": "206"} in found["brands"][0]["models"]
    allb = (await client.call_tool("kn_brands", {})).structured_content
    assert allb["count"] >= 2 and isinstance(allb["brands"][0]["models"], int)


async def test_cities(client, api):
    api["/rest/api/cities/v1/"] = fixture("cities.json")
    r = (await client.call_tool("kn_cities", {})).structured_content
    assert r["cities"][1] == {"id": 2, "slug": "karaj", "name": r["cities"][1]["name"]}


async def test_price_list_flattens_groups_and_filters_year(client, api):
    api["/priceestimator/api/zeroprice/prices/list/"] = fixture("price_list.json")
    r = (await client.call_tool("kn_price_list", {"brand": "Peugeot", "year": 1404})).structured_content
    assert api.calls[0].url.params["brand_en"] == "Peugeot" and "page" not in api.calls[0].url.params
    g = r["groups"][0]
    assert g["brand_en"] == "Peugeot" and g["prices"] and all(p["year"] == 1404 for p in g["prices"])
    assert g["prices"][0]["market_price"] and g["prices"][0]["name"].startswith("Peugeot")
    assert r["has_next_page"] is False


async def test_latest_prices_filters_and_sorts_newest_first(client, api):
    api["/priceestimator/api/zeroprice/last-prices/"] = fixture("last_prices.json")
    r = (await client.call_tool("kn_latest_prices", {"query": "peugeot", "limit": 5})).structured_content
    assert r["matched"] >= 5 and len(r["quotes"]) == 5
    assert all("Peugeot" in q["name"] for q in r["quotes"])
    dates = [q["date"] for q in r["quotes"]]
    assert dates == sorted(dates, reverse=True)


async def test_price_history_trims_series_and_adds_sources(client, api):
    api["/priceestimator/api/zeroprice/prices/averages/daily/"] = fixture("daily.json")
    api["/priceestimator/api/zeroprice/prices/detail/"] = fixture("sources.json")
    r = (
        await client.call_tool("kn_price_history", {"name": "Peugeot 207i Manual TU5P", "year": 1404, "days": 2})
    ).structured_content
    assert list(r["years"]) == ["1404"]
    y = r["years"]["1404"]
    assert y["min_price"] <= y["max_price"] and len(y["daily"]["basic"]) == 2
    assert isinstance(y["daily"]["basic"][0]["price"], int)
    assert r["sources"][0]["price"] == 2850000000
    assert api.calls[1].url.params["price_source"] == "M"


async def test_price_history_unknown_name_is_an_error(client, api):
    api["/priceestimator/api/zeroprice/prices/averages/daily/"] = {"logo": "", "brand_model_fa": "", "years": {}}
    r = await client.call_tool("kn_price_history", {"name": "Nothing Here"})
    assert r.is_error and "kn_price_list" in r.content[0].text


async def test_request_headers_match_the_sites_frontend(api):
    from karnameh_mcp import http

    api["/rest/api/cities/v1/"] = {}
    api["/blog/wp-json/wp/v2/posts"] = []
    await http.fetch("/rest/api/cities/v1/")
    h = api.calls[-1].headers
    assert h["accept"] == "application/json, text/plain, */*"
    assert h["origin"] == "https://karnameh.com" and h["referer"] == "https://karnameh.com/"
    assert (h["sec-fetch-site"], h["sec-fetch-mode"], h["sec-fetch-dest"]) == ("same-site", "cors", "empty")
    assert h["priority"] == "u=1, i" and h["accept-language"].startswith("fa-IR")
    await http.fetch("https://karnameh.com/blog/wp-json/wp/v2/posts")
    h = api.calls[-1].headers
    assert h["accept"] == "*/*" and h["referer"] == "https://karnameh.com/blog/" and "origin" not in h
    assert h["sec-fetch-site"] == "same-origin"
