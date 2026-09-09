"""文章的实体或主题条目原文。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/mediawiki.py", "producer_mediawiki")
fetch = client.wiki_fetch
parse = client.wiki_parse
