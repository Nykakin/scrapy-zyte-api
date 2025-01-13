import pytest
from pytest_twisted import ensureDeferred
from scrapy import Spider, signals
from scrapy.utils.test import get_crawler

try:
    import scrapy.addons  # noqa: F401
except ImportError:
    ADDON_SUPPORT = False
    from . import SETTINGS
else:
    ADDON_SUPPORT = True
    from . import SETTINGS_ADDON as SETTINGS


@pytest.mark.parametrize(
    ("settings", "meta", "headers", "expected"),
    (
        # Default behavior of non-Zyte-API, transparent/automap, and manual
        # Zyte API requests.
        ({}, {}, {}, True),
        (SETTINGS, {"zyte_api_automap": False}, {}, True),
        (SETTINGS, {}, {}, False if ADDON_SUPPORT else True),
        (
            SETTINGS,
            {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True}},
            {},
            False,
        ),
        # Setting ZYTE_API_REFERRER_POLICY to "scrapy-default" changes that
        # for transparent/automap.
        ({"ZYTE_API_REFERRER_POLICY": "scrapy-default"}, {}, {}, True),
        (
            {**SETTINGS, "ZYTE_API_REFERRER_POLICY": "scrapy-default"},
            {"zyte_api_automap": False},
            {},
            True,
        ),
        ({**SETTINGS, "ZYTE_API_REFERRER_POLICY": "scrapy-default"}, {}, {}, True),
        (
            {**SETTINGS, "ZYTE_API_REFERRER_POLICY": "scrapy-default"},
            {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True}},
            {},
            False,
        ),
        # Setting referrer_policy achieves the same.
        ({}, {"referrer_policy": "scrapy-default"}, {}, True),
        (
            SETTINGS,
            {"referrer_policy": "scrapy-default", "zyte_api_automap": False},
            {},
            True,
        ),
        (SETTINGS, {"referrer_policy": "scrapy-default"}, {}, True),
        (
            SETTINGS,
            {
                "referrer_policy": "scrapy-default",
                "zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True},
            },
            {},
            False,
        ),
        # Setting Request.headers["Referer"] works for non-Zyte API and for
        # transparent/automap.
        ({}, {}, {"Referer": "https://example.com"}, "https://example.com"),
        (
            SETTINGS,
            {"zyte_api_automap": False},
            {"Referer": "https://example.com"},
            "https://example.com",
        ),
        (SETTINGS, {}, {"Referer": "https://example.com"}, "https://example.com"),
        (
            SETTINGS,
            {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True}},
            {"Referer": "https://example.com"},
            False,
        ),
        # Setting the header through a Zyte API parameter
        # (customHttpRequestHeaders or requestHeaders) always works.
        (
            SETTINGS,
            {
                "zyte_api_automap": {
                    "customHttpRequestHeaders": [
                        {"name": "Referer", "value": "https://example.com"}
                    ]
                }
            },
            {},
            "https://example.com",
        ),
        (
            SETTINGS,
            {
                "zyte_api_automap": {
                    "requestHeaders": {"referer": "https://example.com"}
                }
            },
            {},
            "https://example.com",
        ),
        (
            SETTINGS,
            {
                "zyte_api": {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "customHttpRequestHeaders": [
                        {"name": "Referer", "value": "https://example.com"}
                    ],
                }
            },
            {},
            "https://example.com",
        ),
        (
            SETTINGS,
            {
                "zyte_api": {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "requestHeaders": {"referer": "https://example.com"},
                }
            },
            {},
            "https://example.com",
        ),
    ),
)
@ensureDeferred
async def test_main(settings, meta, headers, expected, mockserver):
    items = []
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    start_url = mockserver.urljoin("/a")
    follow_up_url = mockserver.urljoin("/b")

    class TestSpider(Spider):
        name = "test"
        start_urls = [start_url]

        def parse(self, response):
            yield response.follow(
                follow_up_url, headers=headers, meta=meta, callback=self.parse_referer
            )

        def parse_referer(self, response):
            referer = response.headers.get(b"Referer", None)
            if referer is not None:
                referer = referer.decode()
            yield {"Referer": referer}

    def track_items(item, response, spider):
        items.append(item)

    crawler = get_crawler(settings_dict=settings, spidercls=TestSpider)
    crawler.signals.connect(track_items, signal=signals.item_scraped)
    await crawler.crawl()

    assert len(items) == 1
    item = items[0]
    if isinstance(expected, str):
        assert item["Referer"] == expected
    elif expected:
        assert item["Referer"] == start_url
    else:
        assert item["Referer"] is None
