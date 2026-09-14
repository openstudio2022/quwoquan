"""文章百科 exact-revision 双证据与结构化语义原文。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/mediawiki.py", "producer_mediawiki")

def fetch(request, transport):
    return client.wiki_fetch(request, transport)

def parse(body, request):
    return client.wiki_parse(body, {**request, "sourceKind": "article_wikipedia"})
