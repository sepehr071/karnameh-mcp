import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_cars_with_filters(client):
    r = (
        await client.call_tool("kn_cars", {"max_price": 3000000000, "sort": "cheapest", "limit": 5})
    ).structured_content
    assert r["total"] > 0 and len(r["ads"]) == 5
    prices = [a["price_toman"] for a in r["ads"]]
    assert prices == sorted(prices) and prices[-1] <= 3000000000


async def test_live_cars_persian_brand_and_detail(client):
    r = (await client.call_tool("kn_cars", {"brand": "پژو", "limit": 3})).structured_content
    assert r["total"] > 0 and all(a["brand_en"] == "Peugeot" for a in r["ads"])
    d = (await client.call_tool("kn_car", {"id": r["ads"][0]["id"]})).structured_content
    assert d["price_toman"] == r["ads"][0]["price_toman"] and d["title"] == r["ads"][0]["title"]


async def test_live_brands_and_cities(client):
    b = (await client.call_tool("kn_brands", {"query": "206"})).structured_content
    assert any(x["brand_en"] == "Peugeot" for x in b["brands"])
    c = (await client.call_tool("kn_cities", {})).structured_content
    assert any(x["slug"] == "tehran" for x in c["cities"])


async def test_live_price_list_and_history(client):
    r = (await client.call_tool("kn_price_list", {"brand": "Peugeot"})).structured_content
    prices = r["groups"][0]["prices"]
    assert prices and prices[0]["market_price"] > 1_000_000_000
    name = prices[0]["name"]
    h = (await client.call_tool("kn_price_history", {"name": name, "days": 5})).structured_content
    assert h["years"] and all(len(s) <= 5 for y in h["years"].values() for s in y["daily"].values())


async def test_live_latest_prices(client):
    r = (await client.call_tool("kn_latest_prices", {"limit": 5})).structured_content
    assert r["matched"] > 100 and len(r["quotes"]) == 5


async def test_live_specs_search_specs_and_compare(client):
    s = (await client.call_tool("kn_specs_search", {"query": "207"})).structured_content
    variants = [c["slug"] for c in s["cars"] if c["variant"]]
    assert len(variants) >= 2
    d = (await client.call_tool("kn_specs", {"slug": "peugeot-207i-automatic-tu5p"})).structured_content
    assert d["specs"]["عملکرد فنی"]["قدرت"].startswith("113") and d["pros"]
    c = (await client.call_tool("kn_compare_specs", {"slugs": variants[:2]})).structured_content
    assert len(c["cars"]) == 2


async def test_live_blog(client):
    a = (await client.call_tool("kn_articles", {"category": "car-reviews", "limit": 3})).structured_content
    assert a["count"] == 3
    r = (await client.call_tool("kn_article", {"id": a["articles"][0]["id"], "max_chars": 800})).structured_content
    assert r["title"] == a["articles"][0]["title"] and len(r["text"]) > 100


async def test_live_movers_city_stats_and_centers(client):
    m = (await client.call_tool("kn_price_movers", {"limit": 3})).structured_content
    assert len(m["movers"]) == 3
    c = (await client.call_tool("kn_city_stats", {})).structured_content
    assert c["total"] > 0 and len(c["cities"]) >= 5
    i = (await client.call_tool("kn_inspection_centers", {"city_id": 1})).structured_content
    assert i["count"] >= 1
