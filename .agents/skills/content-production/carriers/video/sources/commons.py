"""Commons 视频查询适配。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/mediawiki.py", "producer_mediawiki")


def fetch(request, transport):
    return client.commons_fetch(request, transport, "video")


def parse(body, request):
    return client.commons_parse(body, request, "video")
