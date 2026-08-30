"""百科 infobox 是结构化事实的第一手发布位，正文摘要不是。

spec_ref:
- specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025
"""

from __future__ import annotations

import json

from content.source.research.homepage_structured_fact_text import (
    extract_structured_fact_from_baike_infobox,
)


def _infobox_html(pairs: list[tuple[str, list[str]]]) -> bytes:
    """复刻百科页面把 infobox 嵌进转义 JSON 的真实形态。"""

    nodes: list[dict[str, object]] = []
    for key, values in pairs:
        nodes.append(
            {
                "type": "infobox_key",
                "attrs": {"property_id": key, "property_type": "SYSTEM"},
                "children": [{"type": "text", "children": None, "text": key}],
            }
        )
        nodes.append(
            {
                "type": "infobox_value",
                "children": [
                    {
                        "type": "paragraph",
                        "attrs": {},
                        "children": [
                            {"type": "text", "children": None, "text": value}
                            for value in values
                        ],
                    }
                ],
            }
        )
    embedded = json.dumps({"nodes": nodes}, ensure_ascii=False, separators=(",", ":"))
    escaped = embedded.replace('"', '\\"')
    return (
        '<html><body><script>window.__INITIAL_STATE__="'
        + escaped
        + '"</script></body></html>'
    ).encode("utf-8")


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t1
def test_a_ticket_price_declared_only_in_the_infobox_is_admitted() -> None:
    """摘要不含「门票」二字时，infobox 里的票价仍是可核验的一手事实。"""

    html = _infobox_html([("门票价格", ["80元/人"])])

    assert extract_structured_fact_from_baike_infobox(html) == (
        "ticketPriceRange",
        {
            "currency": "CNY",
            "minAmountCents": 8000,
            "maxAmountCents": 8000,
            "free": False,
        },
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t1
def test_seasonal_opening_hours_keep_the_first_declared_window() -> None:
    """旺季/淡季并列时取首个声明窗口，不合并成跨季的假区间。"""

    html = _infobox_html(
        [
            (
                "开放时间",
                [
                    "旺季（4月1日-10月7日）：7:30-18:30",
                    "淡季（10月8日-次年3月31日）：8:00-17:30",
                ],
            )
        ]
    )

    assert extract_structured_fact_from_baike_infobox(html) == (
        "openingHours",
        [{"openMinuteOfDay": 450, "closeMinuteOfDay": 1110}],
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t2
def test_the_governed_field_order_decides_which_declaration_wins() -> None:
    """多个闭集字段同时在场时，采纳顺序与正文提取器一致，不随页面顺序漂移。"""

    html = _infobox_html(
        [
            ("门票价格", ["80元/人"]),
            ("海拔", ["1260米"]),
        ]
    )

    assert extract_structured_fact_from_baike_infobox(html) == (
        "altitudeMeters",
        1260,
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t3
def test_a_value_that_does_not_answer_its_own_key_is_refused() -> None:
    """key 与 value 不同源时拒绝：否则「开放时间」会把邻格的海拔冒名顶替。"""

    html = _infobox_html([("开放时间", ["海拔1260米"])])

    assert extract_structured_fact_from_baike_infobox(html) is None


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t3
def test_an_infobox_without_any_governed_field_is_absent_not_invented() -> None:
    """闭集外的字段一律不投影，缺席就是缺席。"""

    html = _infobox_html(
        [
            ("中文名", ["乐山大佛景区"]),
            ("所属城市", ["乐山市"]),
            ("主要景点", ["灵宝塔"]),
        ]
    )

    assert extract_structured_fact_from_baike_infobox(html) is None


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t4
def test_a_page_without_an_infobox_is_absent() -> None:
    """没有 infobox 的页面不得回落到全文猜测。"""

    body = "乐山大佛，海拔1260米，门票80元。".encode()

    assert extract_structured_fact_from_baike_infobox(body) is None


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t5
def test_a_plain_http_official_site_is_not_admitted_as_a_fact() -> None:
    """官网必须是 https：明文站点不能成为 homepage 的冻结事实。"""

    html = _infobox_html([("官方网站", ["http://www.lsdf517.com/web/index.aspx"])])

    assert extract_structured_fact_from_baike_infobox(html) is None


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-025.t5
def test_an_https_official_site_is_admitted() -> None:
    """https 官网是治理闭集内的 officialWebsite。"""

    html = _infobox_html([("官方网站", ["https://www.lsdf517.com/web/index.aspx"])])

    assert extract_structured_fact_from_baike_infobox(html) == (
        "officialWebsite",
        "https://www.lsdf517.com/web/index.aspx",
    )
