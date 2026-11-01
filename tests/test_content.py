import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

INFO = "/autodetail/api/v1/brand-model/info/"
SLUG = "peugeot-207i-automatic-tu5p"
SPARSE = "peugeot-207i-manual-tu5p"
POSTS = "/blog/wp-json/wp/v2/posts"


async def test_specs_search_puts_variants_first(client, api):
    api["/autodetail/api/v1/brand-model/search/"] = fixture("search.json")
    r = (await client.call_tool("kn_specs_search", {"query": " 207 ", "limit": 3})).structured_content
    assert api.calls[0].url.params["q"] == "207"
    assert r["matched"] == 6 and len(r["cars"]) == 3
    assert r["cars"][0]["variant"] is True and r["cars"][0]["slug"].startswith("peugeot-207i")


async def test_specs_flattens_widgets(client, api):
    api[INFO + SLUG] = fixture("info.json")
    r = (await client.call_tool("kn_specs", {"slug": SLUG})).structured_content
    assert r["score_out_of_10"] == 6 and r["pros"][0] == "ایمنی قابل قبول" and len(r["cons"]) == 2
    assert r["highlights"]["دنده"] == "اتوماتیک"
    assert r["specs"]["عملکرد فنی"]["قدرت"] == "113 اسب بخار"
    assert r["web_reviews"][0]["source"] and r["web_reviews"][0]["text"]
    assert r["url"] == "https://karnameh.com/car-reviews/peugeot/207i/automatic-tu5p"


async def test_specs_bad_slug_is_a_tool_error(client, api):
    r = await client.call_tool("kn_specs", {"slug": "Not A Slug!"})
    assert r.is_error


async def test_compare_specs_lists_only_differences_and_tolerates_missing_data(client, api):
    api[INFO + SLUG] = fixture("info.json")
    api[INFO + SPARSE] = fixture("info_sparse.json")
    r = (await client.call_tool("kn_compare_specs", {"slugs": [SLUG, SPARSE]})).structured_content
    assert [c["slug"] for c in r["cars"]] == [SLUG, SPARSE]
    assert r["cars"][1].get("score_out_of_10") is None
    assert r["specs"]["عملکرد فنی"]["قدرت"] == ["113 اسب بخار", None]
    same = (
        await client.call_tool("kn_compare_specs", {"slugs": [SLUG, SLUG], "only_differences": True})
    ).structured_content
    assert same["specs"] == {}


async def test_articles_resolve_category_and_trim(client, api):
    api["/blog/wp-json/wp/v2/categories"] = [{"id": 118}]
    api[POSTS] = fixture("posts.json")
    r = (
        await client.call_tool("kn_articles", {"query": "کرولا", "category": "car-reviews", "limit": 2})
    ).structured_content
    q = api.calls[-1].url.params
    assert q["categories"] == "118" and q["per_page"] == "2" and q["search"] == "کرولا"
    assert r["count"] == 2 and "<" not in r["articles"][0]["summary"] and r["articles"][0]["url"].startswith("https://")


async def test_articles_page_past_the_end_is_empty(client, api):
    api[POSTS] = lambda request: httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
    r = (await client.call_tool("kn_articles", {"page": 99})).structured_content
    assert r["count"] == 0


async def test_article_is_plain_text_and_truncated(client, api):
    api[f"{POSTS}/74167"] = fixture("post.json")
    r = (await client.call_tool("kn_article", {"id": 74167, "max_chars": 500})).structured_content
    assert "<" not in r["text"] and len(r["text"]) <= 500 and r["truncated"] is True


async def test_price_movers_ranks_recent_changes(client, api):
    api["/priceestimator/api/zeroprice/last-prices/"] = fixture("last_prices.json")
    up = (await client.call_tool("kn_price_movers", {"days": 1})).structured_content
    assert up["newest_quote"] == "2026-10-31" and all(m["date"] == "2026-10-31" for m in up["movers"])
    wide = (await client.call_tool("kn_price_movers", {"days": 30, "limit": 3})).structured_content
    assert [m["change_percent"] for m in wide["movers"]] == [13.64, 5.39, 1.28]
    down = (await client.call_tool("kn_price_movers", {"direction": "down", "days": 30})).structured_content
    assert down["movers"][0]["change_percent"] == 0


async def test_city_stats_counts_each_city(client, api):
    api["/rest/api/cities/v1/"] = fixture("cities.json")
    ads = fixture("ads.json")

    def by_city(request):
        n = 2 if request.url.params["city_slugs"] == "tehran" else 0
        return httpx.Response(200, json={**ads, "car_posts": ads["car_posts"][:n], "total": n})

    api["/post-storage/car-posts/car-post-list/"] = by_city
    r = (await client.call_tool("kn_city_stats", {"brand": "peugeot"})).structured_content
    assert r["total"] == 2 and r["cities"][0]["city"] == "tehran" and r["cities"][0]["cheapest"]["price_toman"]
    assert len(r["cities"]) == 9 and all(c["ads"] == 0 for c in r["cities"][1:])


async def test_inspection_centers(client, api):
    api["/rest/api/evaluation/v1/inspection-center/"] = [
        {"title": "T", "address": "A", "geometry": {"type": "Point", "coordinates": ["51.36", "35.75"]}}
    ]
    r = (await client.call_tool("kn_inspection_centers", {"city_id": 1})).structured_content
    assert api.calls[0].url.params["city_id"] == "1"
    assert r["centers"][0]["lat"] == 35.75 and r["centers"][0]["lon"] == 51.36
