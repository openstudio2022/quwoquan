"""Openverse 的原始作品引用，不把聚合查询结果合为一个作品。"""
import json
from urllib.parse import urlencode


def fetch(request, client):
    query = {"q": request["query"], "page_size": 50, "page": int(request.get("page", 1)), "license": "cc0,by,by-sa"}
    return client.get("https://api.openverse.org/v1/images/?" + urlencode(query))


def parse(body, request):
    rows = []
    for raw in json.loads(body).get("results", []):
        if not raw.get("foreign_landing_url") or not raw.get("url"):
            continue
        identifier = "openverse:" + raw["id"]
        asset = {"id": identifier, "directUrl": raw["url"]}
        for field in ("width", "height"):
            if raw.get(field):
                asset[field] = raw[field]
        row = {"id": identifier, "kind": "image", "source": "openverse", "sourceUrl": raw["foreign_landing_url"],
               "title": raw.get("title") or "", "assets": [asset]}
        for source, target in (("creator", "creator"), ("creator_url", "creatorUrl"), ("license_url", "licenseUrl"), ("license", "license")):
            if raw.get(source):
                row[target] = raw[source]
        rows.append(row)
    return rows, {}
