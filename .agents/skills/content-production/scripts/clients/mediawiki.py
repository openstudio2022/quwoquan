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
    if sum(bool(request.get(key)) for key in ("category", "uploader", "query", "article", "fileTitles")) != 1:
        raise ValueError("Commons 入口必须在 category/uploader/query/article 中五选一")
    query = {"action": "query", "format": "json", "prop": "imageinfo",
             "iiprop": "url|sha1|size|mime|extmetadata|user|timestamp", "iiurlwidth": 1280}
    if request.get("fileTitles"):
        titles = request["fileTitles"]
        if not isinstance(titles, list) or not titles or len(titles) > limit or any(not isinstance(title, str) or not title.startswith("File:") for title in titles):
            raise ValueError("Commons fileTitles 必须是非空 canonical File: 标题列表且不超过 limit")
        query.update(titles="|".join(titles), redirects=1)
    elif request.get("category"):
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
    canonical_title = title if title.startswith("File:") else "File:" + title
    asset = {"id": "commons:" + canonical_title, "directUrl": image["url"], "canonicalFileTitle": canonical_title,
             "pageId": page.get("pageid"), "descriptionUrl": image.get("descriptionurl", ""),
             "metadataCaptured": True, "mediaBytesCaptured": False}
    for source, target in (("sha1", "sha1"), ("size", "bytes"), ("width", "width"), ("height", "height"), ("mime", "mime"), ("duration", "duration"), ("thumburl", "previewUrl")):
        if image.get(source) is not None:
            asset[target] = image[source].lower() if target == "sha1" else image[source]
    row = {"id": "commons:" + canonical_title, "kind": kind, "source": "commons", "title": canonical_title,
           "pageId": page.get("pageid"), "sourceUrl": image.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + quote(canonical_title.replace(" ", "_")), "assets": [asset]}
    asset["extMetadataRaw"] = meta
    for source, target in (("LicenseShortName", "license"), ("LicenseUrl", "licenseUrl"), ("Artist", "creator"), ("Credit", "attribution")):
        raw_value = meta.get(source, {}).get("value")
        value = plain(raw_value)
        if raw_value is not None: asset[target + "Raw"] = raw_value
        if value:
            row[target] = value
            asset[target] = value
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
    returned_titles = set()
    raw_digest = hashlib.sha256(body if isinstance(body, bytes) else str(body).encode()).hexdigest()
    for page in response_pages(body):
        title = str(page.get("title") or "")
        canonical = title if title.startswith("File:") else "File:" + title
        returned_titles.add(canonical)
        if "missing" in page or not page.get("imageinfo"):
            rows.append({"id": "commons:" + canonical, "kind": kind, "source": "commons", "title": canonical, "disposition": "commons_missing", "responseSha256": raw_digest})
            continue
        image = page["imageinfo"][0]
        if not str(image.get("mime", "")).startswith(kind + "/"):
            rows.append({"id": "commons:" + canonical, "kind": kind, "source": "commons", "title": canonical, "disposition": "mime_mismatch", "responseSha256": raw_digest})
            continue
        if request.get("article") and image.get("imagerepository", page.get("imagerepository")) != "shared":
            rows.append({"id": "zhwiki-local:" + canonical, "kind": kind, "source": "wikipedia", "title": canonical, "disposition": "zhwiki_local_upload", "responseSha256": raw_digest})
            continue
        row = commons_row(page, image, kind)
        row.update(disposition="captured", responseSha256=raw_digest)
        required = (row.get("creator"), row.get("license"), row.get("licenseUrl"), row["assets"][0].get("sha1"), row.get("revision"))
        if not all(required): row["disposition"] = "rights_metadata_incomplete"
        rows.append(row)
    for title in request.get("fileTitles") or []:
        if title not in returned_titles:
            rows.append({"id": "commons:" + title, "kind": kind, "source": "commons", "title": title, "disposition": "commons_missing", "responseSha256": raw_digest})
    if request.get("limit") is not None and len(rows) > request["limit"]:
        raise ValueError("Commons 响应超过显式单页 limit")
    return rows, {"responseSha256": raw_digest, "requestedFileTitles": list(request.get("fileTitles") or [])}


def wiki_fetch(request, client):
    """Fetch exact-revision wikitext and revision-bound Parsoid HTML.

    A single REST page/html response cannot prove the revision selected by a
    separate latest query.  The request therefore first resolves one revision,
    then asks MediaWiki for both representations bound to that oldid.
    """
    if not isinstance(request.get("title"), str) or not request["title"].strip():
        raise ValueError("Wikipedia title 必须是非空字符串")
    base = {"action": "query", "format": "json", "formatversion": 2, "variant": "zh-cn", "prop": "info|pageprops|revisions", "redirects": 1, "inprop": "url", "rvprop": "content|ids|timestamp", "rvslots": "main", "titles": request["title"]}
    if request.get("revision") is not None:
        try:
            revision = int(request["revision"])
        except (TypeError, ValueError) as error:
            raise ValueError("Wikipedia revision 必须是正整数") from error
        if revision <= 0:
            raise ValueError("Wikipedia revision 必须是正整数")
        base.update(rvstartid=revision, rvendid=revision)
    query_body = client.get("https://zh.wikipedia.org/w/api.php?" + urlencode(base))
    pages = response_pages(query_body)
    if len(pages) != 1 or "missing" in pages[0]:
        return json.dumps({"contract": "wikipedia_exact_revision_v1", "query": json.loads(query_body), "parsoid": None}, ensure_ascii=False).encode()
    selected = (pages[0].get("revisions") or [{}])[0]
    revid = selected.get("revid")
    if not revid or request.get("revision") is not None and int(revid) != int(request["revision"]):
        raise ValueError("MediaWiki 未返回请求的 exact revision")
    parsoid_url = f"https://zh.wikipedia.org/w/rest.php/v1/revision/{revid}/with_html"
    response_headers = {}
    if hasattr(client, "get_with_headers"):
        response = client.get_with_headers(parsoid_url)
        with_html_body = response.body
        response_headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    else:
        with_html_body = client.get(parsoid_url)
    with_html = json.loads(with_html_body)
    if not isinstance(with_html, dict) or type(with_html.get("id")) is not int or with_html["id"] != revid or not isinstance(with_html.get("html"), str) or not with_html["html"].strip():
        raise ValueError("with_html body id/html 与 exact revision 不一致")
    header_revision = response_headers.get("content-revision-id")
    if header_revision is not None and header_revision != str(revid):
        raise ValueError("with_html content-revision-id 与 exact revision 不一致")
    return json.dumps({"contract": "wikipedia_exact_revision_v1", "revision": revid, "query": json.loads(query_body), "withHtml": {"requestRevision": revid, "url": parsoid_url, "contentRevisionId": header_revision, "response": with_html}}, ensure_ascii=False).encode()


def _revision_content(revision):
    return revision.get("slots", {}).get("main", {}).get("content", revision.get("slots", {}).get("main", {}).get("*", revision.get("*", "")))


def wiki_parse(body, request):
    from core.source_layout import render_source_markdown
    from core.wiki_parsoid import parse_parsoid_layout
    from core.wiki_wikitext import parse_wikitext_layout

    envelope = json.loads(body)
    exact = isinstance(envelope, dict) and envelope.get("contract") == "wikipedia_exact_revision_v1"
    query_data = envelope.get("query") if exact else envelope
    with_html = envelope.get("withHtml") if exact else None
    rows, texts = [], {}
    for page in response_pages(json.dumps(query_data, ensure_ascii=False)):
        if "missing" in page:
            continue
        title = page["title"]
        source_url = page.get("fullurl") or "https://zh.wikipedia.org/wiki/" + quote(title)
        revision = (page.get("revisions") or [{}])[0]
        revid = revision.get("revid")
        raw = _revision_content(revision)
        if not raw.strip():
            continue
        identifier = hashlib.sha256(source_url.encode()).hexdigest()[:24]
        unit = f"sources/wikipedia-{identifier}"
        if exact:
            response = with_html.get("response") if isinstance(with_html, dict) else None
            identities = (envelope.get("revision"), with_html.get("requestRevision") if isinstance(with_html, dict) else None, response.get("id") if isinstance(response, dict) else None, revid)
            if any(value != revid for value in identities) or not isinstance(response.get("html") if isinstance(response, dict) else None, str):
                raise ValueError("wikitext/with_html/request 必须绑定同一 exact revision")
            parsoid_html = response["html"]
            layout = parse_parsoid_layout(parsoid_html, title=title, revision=revid, source_kind=str(request.get("sourceKind") or "wikipedia"))
            from core.wiki_parsoid import build_semantic_document
            semantic = build_semantic_document(layout, parsoid_html, revision=revid)
            texts[f"{unit}/source.wikitext"] = raw
            texts[f"{unit}/source.parsoid.html"] = parsoid_html
            import json as _json
            texts[f"{unit}/source.layout.json"] = _json.dumps(layout, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            texts[f"{unit}/source.semantic.json"] = _json.dumps(semantic, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            rendered = render_source_markdown(layout)
            text = f"# {title}\n\n{rendered}\n"
        else:
            # Explicit migration boundary for archived fixtures.  No extracts are
            # accepted as structure truth; raw wikitext remains the only input.
            layout = parse_wikitext_layout(raw, source_kind=str(request.get("sourceKind") or "wikipedia"), title=title)
            layout["captureCoverage"] = {"wikitext": True, "parsoidHtml": False, "revisionSpecific": bool(revid)}
            layout["semanticParseCoverage"] = {"status": "legacy_wikitext_partial"}
            layout["sourceProfile"] = {"source": "wikipedia", "representation": "wikitext", "revision": revid, "parserProfile": "legacy_migration_only"}
            texts[f"{unit}/source.wikitext"] = raw
            text = f"# {title}\n\n{render_source_markdown(layout)}\n"
        path = f"{unit}/source.md"
        texts[path] = text
        summary = next((str(block.get("text") or "")[:300] for block in layout.get("blocks", []) if block.get("type") == "paragraph"), "")
        row = {"id": "wikipedia:" + str(page.get("pageid") or identifier), "kind": "page", "source": "wikipedia", "sourceUrl": source_url, "title": title, "sourceMarkdownPath": path, "summary": summary, "disambiguation": "disambiguation" in page.get("pageprops", {})}
        if revid:
            row["revision"] = revid
        rows.append(row)
    return rows, texts
