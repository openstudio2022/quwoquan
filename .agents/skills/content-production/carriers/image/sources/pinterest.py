"""公开画板 RSS 的 pin 身份与媒体引用；不把转载者冒充原作者。"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit


def fetch(request, client):
    url = request["url"]
    if urlsplit(url).hostname not in {"pinterest.com", "www.pinterest.com"} or not urlsplit(url).path.endswith(".rss"):
        raise ValueError("仅接受 Pinterest RSS URL")
    return client.get(url)


def parse(body, request):
    root = ET.fromstring(body)
    rows = []
    for item in root.iter("item"):
        url = item.findtext("link") or ""
        description = item.findtext("description") or ""
        image = re.search(r'src=[\"\'](https://i\.pinimg\.com/[^\"\']+)', description)
        if not image or not url.startswith("https://"):
            continue
        pin = url.rstrip("/").rsplit("/", 1)[-1]
        preview = image.group(1).replace("&amp;", "&")
        original = re.sub(r"/\d+x/", "/originals/", preview, count=1)
        rows.append({"id": f"pinterest:{pin}", "kind": "image", "source": "pinterest", "sourceUrl": url,
                     "title": item.findtext("title") or "", "assets": [{"id": f"pinterest:{pin}:image", "directUrl": original, "previewUrl": preview}]})
    return rows, {}
