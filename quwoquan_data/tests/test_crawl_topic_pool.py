from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_data" / "tools"))

import crawl_topic_pool


class CrawlTopicPoolRegressionTest(unittest.TestCase):
    def test_collect_urls_full_mode_not_worse_than_filtered(self) -> None:
        kwargs = dict(
            name="稻城亚丁",
            wiki_title="稻城亚丁",
            baike_item="稻城亚丁",
            aliases=["亚丁风景区"],
            core_tokens=["甘孜", "川西"],
            max_sources=20,
            wiki_link_budget=10,
            baike_link_budget=4,
            wikivoyage_limit=4,
            skip_baike_scrape=True,
            travel_seed_rows=[],
        )
        with (
            patch.object(crawl_topic_pool, "_wiki_title_resolves", return_value=True),
            patch.object(crawl_topic_pool, "_wikivoyage_opensearch_urls", return_value=[]),
            patch.object(
                crawl_topic_pool,
                "_wiki_links_filtered",
                return_value=["https://zh.wikipedia.org/wiki/稻城亚丁自然保护区"],
            ),
            patch.object(
                crawl_topic_pool,
                "_wiki_api_links_raw",
                return_value=[
                    "https://zh.wikipedia.org/wiki/稻城亚丁自然保护区",
                    "https://zh.wikipedia.org/wiki/无关条目",
                ],
            ),
            patch.object(crawl_topic_pool, "_baike_item_links_filtered", return_value=[]),
        ):
            filtered_urls = crawl_topic_pool.collect_urls_for_attraction(
                wiki_expand="filtered",
                **kwargs,
            )
            full_urls = crawl_topic_pool.collect_urls_for_attraction(
                wiki_expand="full",
                **kwargs,
            )

        self.assertGreaterEqual(len(full_urls), len(filtered_urls))
        self.assertIn("https://zh.wikipedia.org/wiki/%E7%A8%BB%E5%9F%8E%E4%BA%9A%E4%B8%81", filtered_urls)
        self.assertIn("https://baike.baidu.com/item/%E7%A8%BB%E5%9F%8E%E4%BA%9A%E4%B8%81", filtered_urls)
        self.assertNotIn("https://zh.wikipedia.org/wiki/无关条目", full_urls)


if __name__ == "__main__":
    unittest.main()
