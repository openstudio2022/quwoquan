"""Commons 图片查询适配；不加载其他载体。"""
from pathlib import Path
import inputs

client = inputs.module(Path(__file__).resolve().parents[3] / "scripts/clients/mediawiki.py", "producer_mediawiki")


def fetch(request, transport):
    return client.commons_fetch(request, transport, "image")


def parse(body, request):
    return client.commons_parse(body, request, "image")
