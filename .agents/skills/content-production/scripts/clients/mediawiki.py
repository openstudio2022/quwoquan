"""MediaWiki 公开响应机械映射；Commons 与百科共用，不判定选材质量。"""
import hashlib
import html
import json
import re
from urllib.parse import quote, urlencode


def plain(value):
    return html.unescape(re.sub(r"<[^>]*>", "", value or "")).strip()


def commons_fetch(request, client, kind):
    limit = request.get("limit")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Commons 单页必须显式声明 1..50 的 limit")
    if sum(bool(request.get(key)) for key in ("category", "uploader", "query", "article")) != 1:
        raise ValueError("Commons 入口必须在 category/uploader/query/article 中四选一")
    query = {"action": "query", "format": "json", "prop": "imageinfo",
             "iiprop": "url|sha1|size|mime|extmetadata|user|timestamp", "iiurlwidth": 1280}
    if request.get("category"):
        query.update(generator="categorymembers", gcmtitle="Category:" + request["category"], gcmtype="file", gcmlimit=limit)
    elif request.get("uploader"):
        query.update(generator="allimages", gaiuser=request["uploader"], gaisort="timestamp", gailimit=limit)
    elif request.get("article"):
        # zhwiki 的 generator=images 与 imageinfo 一次返回条目所引 Commons 文件事实。
        query.update(generator="images", titles=request["article"], gimlimit=limit, redirects=1)
    else:
        query.update(generator="search", gsrnamespace=6, gsrlimit=limit,
                     gsrsearch=request["query"] + (" filetype:video" if kind == "video" else ""))
    continuation = request.get("continue", {})
    if not isinstance(continuation, dict) or any(key not in {"continue", "gcmcontinue", "gaicontinue", "gsroffset", "gimcontinue"} for key in continuation):
        raise ValueError("未知 MediaWiki continuation")
    query.update(continuation)
    host = "zh.wikipedia.org" if request.get("article") else "commons.wikimedia.org"
    return client.get(f"https://{host}/w/api.php?" + urlencode(query))


def commons_row(page, image, kind):
    title = page["title"]
    meta = image.get("extmetadata") or {}
    asset = {"id": "commons:" + title, "directUrl": image["url"]}
    for source, target in (("sha1", "sha1"), ("size", "bytes"), ("width", "width"), ("height", "height"), ("mime", "mime"), ("duration", "duration"), ("thumburl", "previewUrl")):
        if image.get(source) is not None:
            asset[target] = image[source].lower() if target == "sha1" else image[source]
    row = {"id": "commons:" + title, "kind": kind, "source": "commons", "title": title,
           "sourceUrl": "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_")), "assets": [asset]}
    for source, target in (("LicenseShortName", "license"), ("LicenseUrl", "licenseUrl"), ("Artist", "creator")):
        value = plain(meta.get(source, {}).get("value"))
        if value:
            row[target] = value
    for source, target in (("user", "uploader"), ("timestamp", "revision")):
        if image.get(source):
            row[target] = image[source]
    if meta.get("ImageDescription"):
        asset["description"] = plain(meta["ImageDescription"].get("value"))
    return row


def response_pages(body):
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("MediaWiki 顶层必须是对象")
    if "error" in data or "errors" in data:
        raise ValueError(f"MediaWiki API 错误：{data.get('error', data.get('errors'))}")
    query = data.get("query", {})
    if not isinstance(query, dict):
        raise ValueError("MediaWiki query 必须是对象")
    pages = query.get("pages", {})
    if not isinstance(pages, (dict, list)):
        raise ValueError("MediaWiki pages 必须是对象或数组")
    rows = list(pages.values()) if isinstance(pages, dict) else pages
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("MediaWiki page 必须是对象")
    return rows


def commons_parse(body, request, kind):
    rows = []
    for page in response_pages(body):
        image = (page.get("imageinfo") or [page])[0]
        if not str(image.get("mime", "")).startswith(kind + "/"):
            continue
        if request.get("article") and image.get("imagerepository", page.get("imagerepository")) != "shared":
            continue  # 条目本地上传不能冒充 Commons 文件身份。
        rows.append(commons_row(page, image, kind))
    if request.get("limit") is not None and len(rows) > request["limit"]:
        raise ValueError("Commons 响应超过显式单页 limit")
    return rows, {}


def wiki_fetch(request, client):
    query = {"action": "query", "format": "json", "variant": "zh-cn", "prop": "extracts|info|pageprops|revisions",
             "explaintext": 1, "redirects": 1, "inprop": "url", "rvprop": "content|ids", "rvslots": "main", "titles": request["title"]}
    return client.get("https://zh.wikipedia.org/w/api.php?" + urlencode(query))


def infobox(raw):
    start = re.search(r"\{\{\s*(?:Infobox|信息框)", raw, re.I)
    if not start:
        return ""
    depth, position = 0, start.start()
    while position < len(raw):
        if raw.startswith("{{", position):
            depth += 1
            position += 2
        elif raw.startswith("}}", position):
            depth -= 1
            position += 2
            if depth == 0:
                return raw[start.start():position]
        else:
            position += 1
    return raw[start.start():]


def wiki_parse(body, request):
    rows, texts = [], {}
    for page in response_pages(body):
        if "missing" in page or not page.get("extract", "").strip():
            continue
        title = page["title"]
        source_url = page.get("fullurl") or "https://zh.wikipedia.org/wiki/" + quote(title)
        revision = (page.get("revisions") or [{}])[0]
        raw = revision.get("slots", {}).get("main", {}).get("*", revision.get("*", ""))
        text = f"# {title}\n\n{page['extract']}\n"
        box = infobox(raw)
        if box:
            text += f"\n## 结构化来源（原文）\n\n```wikitext\n{box}\n```\n"
        identifier = hashlib.sha256(source_url.encode()).hexdigest()[:24]
        path = f"sources/wikipedia-{identifier}/source.md"
        texts[path] = text
        row = {"id": "wikipedia:" + str(page.get("pageid") or identifier), "kind": "page", "source": "wikipedia",
               "sourceUrl": source_url, "title": title, "sourceMarkdownPath": path,
               "summary": page["extract"][:300], "disambiguation": "disambiguation" in page.get("pageprops", {})}
        if revision.get("revid"):
            row["revision"] = revision["revid"]
        rows.append(row)
    return rows, texts
