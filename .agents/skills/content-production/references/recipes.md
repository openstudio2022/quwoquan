# 轮次配方：一次性脚本的可重建模板

r03 试轮的最大浪费是主会话临场重写约 400 行取证/下载/拼装脚本。本文件把这些脚本作为**模板**收录：每个会话按需复制到 `/tmp/qwq_rNN/` 运行，产物只落 `.qwq_output/data/local/workspace/<round>/`。它们不进仓库、不进 `.qwq_output`，满足「可由 Skill reference 重建」；仓内不新增抓取器（[sourcing.md](sourcing.md) 通用约束）。模板只做机械事：出网取回、落盘、拼装、批处理；所有语义判断（选实体、看图、定角度标题、写正文、评分）仍由 AI 完成。

约定：`QWQ_WS=.qwq_output/data/local/workspace/<round>`（绝对路径），`QWQ_ROUND=rNN`，`REPO` 为仓根。所有脚本用 `python3`（3.13，仓库环境）；出网统一带合规 UA、同站串行、0.7 s 间隔、SSL/超时靶向重试 3 次。后台任务用宿主工具级后台（`block_until_ms`），不用 shell `&`/`nohup`（会随工具 shell 退出被回收）。

## 0. 公共头（每个脚本开头）

```python
import json, os, re, sys, time, hashlib, urllib.parse, urllib.request, ssl
UA = "QuwoquanContentProducer/1.0 (https://quwoquan.example; data-engineering contact) python-urllib"
WS = os.environ["QWQ_WS"]; ROUND = os.environ.get("QWQ_ROUND", "rNN")
for d in ("api", "sources", "downloads", "downloads/preview"): os.makedirs(f"{WS}/{d}", exist_ok=True)
_last = {}
def get(url, dest=None, timeout=120, gap=0.7, retries=3, headers=None):
    host = urllib.parse.urlsplit(url).netloc
    wait = gap - (time.time() - _last.get(host, 0));  time.sleep(wait) if wait > 0 else None
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(); _last[host] = time.time()
                if dest: open(dest, "wb").write(body)
                return body
        except (ssl.SSLError, TimeoutError, ConnectionResetError, urllib.error.URLError) as e:
            if attempt == retries - 1 or getattr(e, "code", 0) in (403, 404, 429, 503): raise
            time.sleep(2 * (attempt + 1))
def jget(url, **kw): return json.loads(get(url, **kw))
def dump(name, obj): p = f"{WS}/api/{name}"; json.dump(obj, open(p, "w"), ensure_ascii=False, indent=1); return p
def slug(s): return re.sub(r"[^\w\u4e00-\u9fff]+", "_", s).strip("_")[:80]
FENCE = chr(96) * 3  # Markdown 代码围栏；模板本身在代码块里，不能直接写三个反引号
```

把本文件的代码块抽成脚本（公共头 + 各段，按出现顺序命名）：

```text
python3 - <<'EOF'
import re; md = open("<REPO>/.agents/skills/content-production/references/recipes.md").read()
blocks = re.findall(r"```python\n(.*?)```", md, re.S); header = blocks[0]
names = ["wiki_acquire","evidence_append","toutiao_acquire","commons_search","creator_bulk","download","sheets","build_inputs","prompts","seal_review","publish"]
for name, body in zip(names, blocks[1:]): open(f"/tmp/qwq_rNN/{name}.py", "w").write(header + "\n" + body)
EOF
```

## 1. `wiki_acquire.py` — 维基条目正文 + 信息框 + 条目配图元数据

输入 `api/<round>_pick.json`：`[{"name":"三峡大坝","title":"长江三峡水利枢纽工程"}]`（`title` 缺省用 `name`）。输出 `sources/<name>.source.md`（H1 + 正文 + `## 信息区（原文）`）与 `api/<round>_entities.json`（含 `revid`、`extractChars`、`infobox`、`images[]` 带 `sha1/bytes/w/h/mime/license/licenseUrl/artist/description`）。`## 信息区取证` 由 AI 亲笔用 `evidence_append.py` 追加。

```python
WIKI = "https://zh.wikipedia.org/w/api.php?format=json&variant=zh-cn&"
COMMONS = "https://commons.wikimedia.org/w/api.php?format=json&"
def infobox_block(wikitext):
    i = wikitext.find("{{Infobox");  i = wikitext.find("{{infobox") if i < 0 else i
    if i < 0: return ""
    depth, j = 0, i
    while j < len(wikitext):
        if wikitext.startswith("{{", j): depth += 1; j += 2
        elif wikitext.startswith("}}", j):
            depth -= 1; j += 2
            if depth == 0: return wikitext[i:j]
        else: j += 1
    return wikitext[i:]
def imageinfo(titles):
    out = []
    for k in range(0, len(titles), 50):
        q = COMMONS + "action=query&prop=imageinfo&iiprop=url|sha1|size|mime|extmetadata&iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|ImageDescription&titles=" + urllib.parse.quote("|".join(titles[k:k+50]))
        for p in jget(q)["query"].get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0];  em = ii.get("extmetadata", {})
            if not ii.get("url") or not str(ii.get("mime", "")).startswith(("image/jpeg", "image/png", "video/")): continue
            strip = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()
            out.append({"title": p["title"], "url": ii["url"], "sha1": ii.get("sha1"), "bytes": ii.get("size"), "w": ii.get("width"), "h": ii.get("height"),
                        "mime": ii["mime"], "license": em.get("LicenseShortName", {}).get("value", ""),
                        "licenseUrl": em.get("LicenseUrl", {}).get("value", "").replace("http://", "https://"),
                        "artist": strip(em.get("Artist", {}).get("value")), "description": strip(em.get("ImageDescription", {}).get("value"))[:300]})
    return out
rows = []
for pick in json.load(open(f"{WS}/api/{ROUND}_pick.json")):
    name, title = pick["name"], pick.get("title") or pick["name"]
    t = urllib.parse.quote(title)
    page = next(iter(jget(WIKI + f"action=query&prop=extracts|info|images&explaintext=1&redirects=1&inprop=url&imlimit=50&titles={t}")["query"]["pages"].values()))
    if "missing" in page or not page.get("extract", "").strip(): print("SKIP", name, "missing/empty"); continue
    wikitext = jget(WIKI + f"action=parse&page={urllib.parse.quote(page['title'])}&prop=wikitext&section=0")["parse"]["wikitext"]["*"]
    box = infobox_block(wikitext)
    imgs = [im["title"] for im in page.get("images", []) if not re.search(r"\.(svg|gif|ogg|mid)$", im["title"], re.I)]
    md = f"# {page['title']}\n\n{page['extract'].strip()}\n"
    if box: md += f"\n## 信息区（原文）\n\n{FENCE}\n{box}\n{FENCE}\n"
    md += f"\n- 来源条目：zh.wikipedia「{page['title']}」revid {page['lastrevid']}\n"
    open(f"{WS}/sources/{name}.source.md", "w").write(md)
    rows.append({"name": name, "title": page["title"], "url": page["fullurl"], "revid": page["lastrevid"], "extractChars": len(page["extract"]),
                 "infobox": bool(box), "images": imageinfo(imgs) if imgs else []})
    print(f"OK {name} {len(page['extract'])}字 infobox={bool(box)} images={len(rows[-1]['images'])}")
dump(f"{ROUND}_entities.json", rows)
```

`evidence_append.py`（AI 亲笔取证；输入 `api/<round>_evidence.json` = `{"三峡大坝":["所在地：湖北省宜昌市夷陵区","坝高：181 米", ...]}`）：

```python
for name, lines in json.load(open(f"{WS}/api/{ROUND}_evidence.json")).items():
    p = f"{WS}/sources/{name}.source.md"; md = open(p).read()
    if "## 信息区取证" in md: continue
    body, _, tail = md.rpartition("\n- 来源条目：")
    open(p, "w").write(body + "\n\n## 信息区取证\n\n" + "\n".join(f"- {l}" for l in lines) + "\n\n- 来源条目：" + tail)
```

## 2. `toutiao_acquire.py` — 头条百科条目（维基缺条目或过薄时）

输入 `api/<round>_pick_toutiao.json`（同形，`title` 写头条百科的条目名，如「安顺龙宫」「宜春明月山」）。页内 `var __prefetch_doc_data__ = {...}` 是结构化真相：`VersionContent.Content` 与 `.Infobox` 是富文本节点树的 JSON 字符串，`HeadImageList[]` 带 `License`/`Copyright`，`ReferenceList[]` 是条目引用。输出 `sources/<name>.toutiao.source.md`（与维基产物并存，由 `build_inputs` 按 `plan.json` 的 `source` 选用）与 `api/<round>_toutiao.json`。条目不存在返回 404，按候选级放弃。

```python
def prefetch_doc_data(html):
    """页内 `var __prefetch_doc_data__ = {...};` 是唯一结构化真相：用括号配对取出该对象。"""
    i = html.find("__prefetch_doc_data__"); j = html.find("{", i)
    depth, k, instr, esc = 0, j, False, False
    while k < len(html):
        c = html[k]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: break
        k += 1
    return json.loads(html[j:k + 1])
def node_text(node):
    if isinstance(node, list): return "".join(node_text(n) for n in node)
    if not isinstance(node, dict): return ""
    return (node.get("text") or "") + node_text(node.get("children") or [])
def content_lines(content_nodes):
    lines = []
    for n in content_nodes:
        t = n.get("type", ""); txt = node_text(n).strip()
        if not txt: continue
        if t.startswith("heading"):
            level = int(n.get("attrs", {}).get("level") or 2); lines.append("#" * min(level + 1, 4) + " " + txt)
        elif t in ("paragraph", "blockquote", "list_item", "table_cell"): lines.append(txt)
        else: lines.append(txt)
    return lines
def infobox_pairs(infobox_nodes):
    pairs, key = [], None
    for n in infobox_nodes:
        t = n.get("type", "")
        if t == "infobox_key": key = node_text(n).strip()
        elif t == "infobox_value" and key: pairs.append((key, node_text(n).strip())); key = None
    return pairs
rows = []
for pick in json.load(open(f"{WS}/api/{ROUND}_pick_toutiao.json")):
    name = pick["name"]; query = pick.get("title") or name; url = "https://www.baike.com/wiki/" + urllib.parse.quote(query)
    html = get(url, dest=f"{WS}/api/toutiao_{name}.html").decode("utf-8", "replace")
    if "__prefetch_doc_data__" not in html: print("SKIP", name, "no doc data"); continue
    d = prefetch_doc_data(html); vc = d.get("VersionContent") or {}; title = vc.get("Title") or (d.get("DocMeta") or {}).get("Title") or query
    if query[:2] not in title and name[:2] not in title: print("SKIP", name, "title mismatch:", title); continue
    content = json.loads(vc.get("Content") or "[]"); infobox = json.loads(vc.get("Infobox") or "[]")
    lines = content_lines(content); pairs = infobox_pairs(infobox)
    md = f"# {title}\n\n" + "\n\n".join(lines) + "\n"
    if pairs: md += f"\n## 信息区（原文）\n\n{FENCE}\n" + "\n".join(f"{k}：{v}" for k, v in pairs) + f"\n{FENCE}\n"
    refs = [r.get("URL") for r in (vc.get("ReferenceList") or []) if r.get("URL")]
    md += f"\n- 来源条目：头条百科「{title}」 {url}（VersionNumber {d.get('VersionNumber')}）\n"
    open(f"{WS}/sources/{name}.toutiao.source.md", "w").write(md)
    imgs = [{"url": "https:" + im["URL"] if im.get("URL", "").startswith("//") else im.get("URL"), "w": im.get("Width"), "h": im.get("Height"), "license": im.get("License", ""), "copyright": im.get("Copyright", ""), "name": im.get("Name")} for im in (vc.get("HeadImageList") or [])]
    rows.append({"name": name, "title": title, "url": url, "version": d.get("VersionNumber"), "chars": sum(len(l) for l in lines), "infobox": len(pairs), "references": refs[:10], "images": imgs})
    print("OK", name, "→", title, rows[-1]["chars"], "字", "infobox", len(pairs), "imgs", len(imgs))
dump(f"{ROUND}_toutiao.json", rows)
```

ingest 行：`{"kind":"page","sourceUrl":url,"title":name,"sourceMarkdownPath":...,"license":"头条百科版权声明（版权保留）","licenseUrl":"https://www.baike.com/","creator":"头条百科条目贡献者","relevance":"实体条目，事实来源"}`；头图 `license` 为空或 `copyright=no_copyright` 时不作资产。

## 3. `commons_search.py` — 类目/检索取文件（图片或视频）

```python
COMMONS = "https://commons.wikimedia.org/w/api.php?format=json&"
def commons_files(*, category=None, search=None, video=False, limit=50):
    if category: gen = f"generator=categorymembers&gcmtitle={urllib.parse.quote('Category:' + category)}&gcmtype=file&gcmlimit={limit}"
    else: gen = f"generator=search&gsrnamespace=6&gsrsearch={urllib.parse.quote(search + (' filetype:video' if video else ''))}&gsrlimit={limit}"
    data = jget(COMMONS + "action=query&" + gen + "&prop=imageinfo&iiprop=url|sha1|size|mime|extmetadata&iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|ImageDescription")
    rows = []
    for p in data.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]; em = ii.get("extmetadata", {}); strip = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()
        rows.append({"title": p["title"], "url": ii.get("url"), "sha1": ii.get("sha1"), "bytes": ii.get("size"), "w": ii.get("width"), "h": ii.get("height"), "mime": ii.get("mime"),
                     "duration": ii.get("duration"), "license": em.get("LicenseShortName", {}).get("value", ""), "licenseUrl": em.get("LicenseUrl", {}).get("value", "").replace("http://", "https://"),
                     "artist": strip(em.get("Artist", {}).get("value")), "description": strip(em.get("ImageDescription", {}).get("value"))[:300]})
    return rows
# 用法：python3 commons_search.py "<实体名或英文名>" [--video] [--category <类目>]
args = sys.argv[1:]; video = "--video" in args; cat = args[args.index("--category") + 1] if "--category" in args else None
term = [a for a in args if not a.startswith("--") and a != cat][0] if not cat else None
rows = commons_files(category=cat, search=term, video=video)
rows = [r for r in rows if r["url"] and (r["bytes"] or 0) <= 536870912 and (video or (r["w"] or 0) >= 1600)]
dump(f"{ROUND}_commons_{slug(cat or term)}{'_video' if video else ''}.json", rows); print(len(rows), "候选")
```

## 4. `creator_bulk.py` — 创作者/站点批量（反转「先定实体再找图」）

四条路径都输出统一行：`{"source","creator","creatorUrl","title","url","directUrl","sha1","bytes","w","h","mime","license","licenseUrl","description","duration","views","likes","comments","favorites","creatorFollowers","publishedAt","accessPolicy"}`，汇总到 `frontier/creators.json`（`{"generatedAt","rows":[...]}`），AI 再按文件名/标题把行归到实体（`entityGuess` 字段由 AI 写，不由脚本猜）。

```python
FR = os.path.join(os.path.dirname(WS), "frontier"); os.makedirs(FR, exist_ok=True)
def commons_uploader(user, cap=2500):
    rows, cont = [], ""
    while len(rows) < cap:
        q = f"https://commons.wikimedia.org/w/api.php?format=json&action=query&list=allimages&aiuser={urllib.parse.quote(user)}&aisort=timestamp&aidir=descending&ailimit=500&aiprop=url|sha1|size|mime|timestamp|extmetadata&aiextmetadatafilter=LicenseShortName|LicenseUrl|ImageDescription{cont}"
        d = jget(q)
        for ai in d["query"]["allimages"]:
            if not ai.get("mime", "").startswith("image/jpeg") or (ai.get("width") or 0) < 1600: continue
            em = ai.get("extmetadata", {})
            rows.append({"source": "commons", "creator": user, "creatorUrl": f"https://commons.wikimedia.org/wiki/User:{urllib.parse.quote(user)}", "title": ai["title"],
                         "url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(ai["title"].replace(" ", "_")), "directUrl": ai["url"], "sha1": ai["sha1"], "bytes": ai["size"], "w": ai["width"], "h": ai["height"], "mime": ai["mime"],
                         "license": em.get("LicenseShortName", {}).get("value", ""), "licenseUrl": em.get("LicenseUrl", {}).get("value", "").replace("http://", "https://"),
                         "description": re.sub(r"<[^>]+>", "", em.get("ImageDescription", {}).get("value", ""))[:200], "publishedAt": ai["timestamp"], "accessPolicy": "open"})
        if "continue" not in d: break
        cont = "&aicontinue=" + urllib.parse.quote(d["continue"]["aicontinue"])
    return rows
def ytdlp_json(url, flat=True):
    import subprocess
    cmd = ["yt-dlp", "-J", "--no-warnings", "--user-agent", UA] + (["--flat-playlist"] if flat else []) + [url]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600).stdout)
def youtube_channel(handle_url, cap=200):
    d = ytdlp_json(handle_url.rstrip("/") + "/videos"); rows = []
    for e in (d.get("entries") or [])[:cap]:
        rows.append({"source": "youtube", "creator": d.get("uploader") or d.get("channel"), "creatorUrl": d.get("uploader_url") or handle_url, "title": e.get("title"), "url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
                     "directUrl": None, "duration": e.get("duration"), "views": e.get("view_count"), "license": None, "accessPolicy": "tos_restricted"})
    return rows
def youtube_cc_search(query):  # 检索页自带 Creative Commons 过滤（sp=EgIwAQ%3D%3D），比频道全集更直接
    d = ytdlp_json("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgIwAQ%253D%253D")
    return [{"source": "youtube", "creator": e.get("channel"), "creatorUrl": e.get("channel_url"), "title": e.get("title"), "url": f"https://www.youtube.com/watch?v={e['id']}", "directUrl": None, "duration": e.get("duration"), "views": e.get("view_count"), "license": None, "accessPolicy": "tos_restricted"} for e in (d.get("entries") or []) if e]
def youtube_detail(watch_url):  # license 只在单条元数据里；只取 "Creative Commons" 的下载
    d = ytdlp_json(watch_url, flat=False)
    return {"license": d.get("license"), "views": d.get("view_count"), "likes": d.get("like_count"), "comments": d.get("comment_count"), "creatorFollowers": d.get("channel_follower_count"),
            "publishedAt": d.get("upload_date"), "duration": d.get("duration"), "w": d.get("width"), "h": d.get("height"), "bytes": d.get("filesize_approx"), "description": (d.get("description") or "")[:300]}
def bilibili_space(mid, cap=200):
    d = ytdlp_json(f"https://space.bilibili.com/{mid}/video"); rows = []
    for e in (d.get("entries") or [])[:cap]:
        rows.append({"source": "bilibili", "creator": d.get("uploader") or str(mid), "creatorUrl": f"https://space.bilibili.com/{mid}", "title": e.get("title"), "url": e.get("url"), "directUrl": None,
                     "duration": e.get("duration"), "license": "Bilibili 用户协议（版权保留）", "licenseUrl": "https://www.bilibili.com/blackboard/protocal/activity-yxU2f7Wbm.html", "accessPolicy": "tos_restricted"})
    return rows
def tuchong_tag(tag, pages=3, order="weekly"):
    rows = []
    for page in range(1, pages + 1):
        d = jget(f"https://tuchong.com/rest/tags/{urllib.parse.quote(tag)}/posts?page={page}&count=20&order={order}", headers={"Accept": "application/json"}, gap=3.0)
        sites = d.get("siteList") if isinstance(d.get("siteList"), dict) else {}
        if not d.get("postList") and order == "weekly": return tuchong_tag(tag, pages=pages, order="new")
        for post in d.get("postList") or []:
            site = sites.get(str(post.get("author_id") or post.get("site_id") or "")) or {}
            for im in post.get("images") or []:
                rows.append({"source": "tuchong", "creator": site.get("name"), "creatorUrl": f"https://tuchong.com/{site.get('site_id')}/", "title": (post.get("title") or post.get("excerpt") or "")[:80], "url": post.get("url"),
                             "directUrl": f"https://photo.tuchong.com/{im.get('user_id')}/f/{im.get('img_id')}.jpg", "w": im.get("width"), "h": im.get("height"), "mime": "image/jpeg",
                             "license": "图虫用户协议（版权保留）", "licenseUrl": "https://tuchong.com/agreement/", "description": (post.get("excerpt") or "")[:200],
                             "views": post.get("views"), "likes": post.get("favorites"), "comments": post.get("comments"), "favorites": post.get("collected"), "creatorFollowers": site.get("followers"),
                             "publishedAt": post.get("published_at"), "accessPolicy": "tos_restricted"})
    return rows
def pinterest_rss(feed_url):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(get(feed_url)); rows = []
    for item in root.iter("item"):
        desc = item.findtext("description") or ""; m = re.search(r'src="(https://i\.pinimg\.com/[^"]+)"', desc)
        if not m: continue
        thumb = m.group(1); original = re.sub(r"/\d+x/", "/originals/", thumb)
        rows.append({"source": "pinterest", "creator": root.findtext("channel/title"), "creatorUrl": root.findtext("channel/link"), "title": (item.findtext("title") or "")[:80], "url": item.findtext("link"), "directUrl": original,
                     "mime": "image/jpeg", "license": "Pinterest 服务条款（转载物，原始权利未知）", "licenseUrl": "https://policy.pinterest.com/terms-of-service", "description": re.sub(r"<[^>]+>", "", desc)[:200],
                     "publishedAt": item.findtext("pubDate"), "accessPolicy": "robots_disallowed"})
    return rows
def openverse(q, pages=2):
    rows = []
    for page in range(1, pages + 1):
        d = jget(f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(q)}&license=cc0,by,by-sa&page_size=50&page={page}")
        for r in d.get("results", []):
            rows.append({"source": "openverse:" + r.get("source", ""), "creator": r.get("creator"), "creatorUrl": r.get("creator_url"), "title": r.get("title"), "url": r.get("foreign_landing_url"), "directUrl": r.get("url"),
                         "w": r.get("width"), "h": r.get("height"), "mime": r.get("filetype"), "license": (r.get("license") or "").upper().replace("BY", "CC BY").replace("CC0", "CC0") + " " + (r.get("license_version") or ""),
                         "licenseUrl": r.get("license_url"), "description": (r.get("title") or "")[:200], "accessPolicy": "open"})
    return rows
def inaturalist(place_id, taxon=None, pages=2):
    rows = []
    for page in range(1, pages + 1):
        d = jget(f"https://api.inaturalist.org/v1/observations?place_id={place_id}&quality_grade=research&photo_license=cc0,cc-by,cc-by-sa&photos=true&per_page=100&page={page}&order_by=votes" + (f"&taxon_id={taxon}" if taxon else ""))
        for o in d.get("results", []):
            for ph in o.get("photos", [])[:1]:
                rows.append({"source": "inaturalist", "creator": (o.get("user") or {}).get("login"), "creatorUrl": "https://www.inaturalist.org/people/" + str((o.get("user") or {}).get("login")), "title": (o.get("taxon") or {}).get("preferred_common_name") or (o.get("taxon") or {}).get("name"),
                             "url": o.get("uri"), "directUrl": (ph.get("url") or "").replace("square", "original"), "mime": "image/jpeg", "license": ph.get("license_code", "").upper().replace("CC-BY", "CC BY").replace("CC0", "CC0"), "licenseUrl": None,
                             "description": (o.get("place_guess") or "")[:200], "likes": o.get("faves_count"), "publishedAt": o.get("observed_on"), "accessPolicy": "open"})
    return rows
# 用法：编辑下方清单后运行；每次运行覆盖同源行、保留其它源的旧行。
PLAN = {"commons": ["Zhangzhugang", "Huangdan2060", "Gisling"], "youtube": [], "bilibili": [], "tuchong": ["川西", "新疆", "航拍"], "pinterest": [], "openverse": [], "inaturalist": []}
path = f"{FR}/creators.json"; old = json.load(open(path)) if os.path.exists(path) else {"rows": []}
rows = [r for r in old["rows"] if r["source"].split(":")[0] not in PLAN or not PLAN[r["source"].split(":")[0]]]
for u in PLAN["commons"]: rows += commons_uploader(u); print("commons", u, len(rows))
for u in PLAN["youtube"]: rows += youtube_channel(u); print("youtube", u, len(rows))
for m in PLAN["bilibili"]: rows += bilibili_space(m); print("bilibili", m, len(rows))
for t in PLAN["tuchong"]: rows += tuchong_tag(t); print("tuchong", t, len(rows))
for f in PLAN["pinterest"]: rows += pinterest_rss(f); print("pinterest", f, len(rows))
for q in PLAN["openverse"]: rows += openverse(q); print("openverse", q, len(rows))
for p in PLAN["inaturalist"]: rows += inaturalist(p); print("inaturalist", p, len(rows))
json.dump({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows": rows}, open(path, "w"), ensure_ascii=False, indent=1); print("total", len(rows), "->", path)
```

读回归实体：`jq -r '.rows[] | select(.source=="commons") | .title' frontier/creators.json | sed 's/^File://' | cut -c1-60 | sort | uniq -c | sort -rn | head -80` 看文件名前缀分布，AI 把前缀映射到实体名写成 `frontier/creator_entity_map.json`（`{"Anshun Longgong":"龙宫","Mount Heng (Hunan)":"衡山"}`），每轮从中挑「≥3 张切题图」的实体。

## 5. `download.py` — 串行下载 + sha1 核验 + 512 MiB 预过滤

输入 `api/<round>_downloads.json`：`{"images":[{"entity","role":"homepage_cover|article_figure|image_work","title","url","sha1","bytes","w","h","mime","license","licenseUrl","artist","description"}],"videos":[...同形, "role":"video"]}`。输出同名文件加 `file/status/sha1Match` 字段；`bytes > 536870912` 直接 `status=skip_oversize` 不下载。

```python
p = f"{WS}/api/{ROUND}_downloads.json"; plan = json.load(open(p))
for kind in ("images", "videos"):
    for row in plan.get(kind, []):
        if row.get("status") == "ok": continue
        if (row.get("bytes") or 0) > 536870912: row["status"] = "skip_oversize"; continue
        ext = os.path.splitext(urllib.parse.unquote(row["url"]))[1].lower() or (".jpg" if kind == "images" else ".mp4")
        row["file"] = f"{WS}/downloads/{row['entity']}__{row['role']}__{slug(row.get('title') or os.path.basename(row['url']))}{ext}"
        try:
            body = get(row["url"], dest=row["file"], timeout=600)
            row["status"] = "ok"; row["sha1Match"] = (hashlib.sha1(body).hexdigest() == row["sha1"]) if row.get("sha1") else None
            if row["sha1Match"] is False: row["status"] = "source_sha1_drift"
        except Exception as e: row["status"] = f"error:{type(e).__name__}:{str(e)[:80]}"
        print(row["status"], row["entity"], row["role"], row.get("bytes"))
        json.dump(plan, open(p, "w"), ensure_ascii=False, indent=1)
```

YouTube/Bilibili 下载不走这里：`yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]" --merge-output-format mp4 --user-agent "$UA" -o "$QWQ_WS/downloads/<实体>__video__<slug>.mp4" <url>`。

## 6. `sheets.py` — 预览拼图（主会话看图用）

把下载图按 20 张一页拼成 `downloads/preview/sheet_NN.jpg`（每格 480 px 宽，左上角写序号），视频抽帧 `ffmpeg -ss 3 -i <file> -frames:v 1 -vf scale=480:-1 <poster>.jpg` 后同法拼 `posters.jpg`。宿主看图工具读 jpg，不读 webp。

```python
from PIL import Image, ImageDraw
rows = [r for k in ("images",) for r in json.load(open(f"{WS}/api/{ROUND}_downloads.json"))[k] if r.get("status") == "ok"]
index = [{"idx": i, "entity": r["entity"], "role": r["role"], "title": r["title"], "file": r["file"], "w": r.get("w"), "h": r.get("h"), "license": r.get("license"), "artist": r.get("artist")} for i, r in enumerate(rows)]
dump(f"{ROUND}_sheet_index.json", index)
CELL, COLS, PER = 480, 4, 20
for s in range(0, len(index), PER):
    batch = index[s:s+PER]; sheet = Image.new("RGB", (CELL * COLS, 360 * ((len(batch) + COLS - 1) // COLS)), "white"); d = ImageDraw.Draw(sheet)
    for j, r in enumerate(batch):
        try:
            with Image.open(r["file"]) as im:
                im.draft("RGB", (CELL, CELL)); im = im.convert("RGB"); im.thumbnail((CELL - 8, 330))
                x, y = (j % COLS) * CELL, (j // COLS) * 360; sheet.paste(im, (x + 4, y + 24)); d.text((x + 6, y + 4), f"#{r['idx']} {r['entity']} {r['role']} {r['w']}x{r['h']}", fill="black")
        except Exception as e: d.text((x + 6, y + 4), f"#{r['idx']} ERR {e}", fill="red")
    out = f"{WS}/downloads/preview/sheet_{s // PER:02d}.jpg"; sheet.save(out, quality=80); print(out)
```

看完后 AI 写 `api/<round>_decisions.json`：`{"<idx>": {"use": true, "watermarkStatus": "absent", "watermarkKind": "none", "relevance": "…", "note": "…"}}`；`use=false` 的候选级放弃不落台账。

## 7. `build_inputs.py` — 拼 round.json 与四份 ingest.json

输入：`api/<round>_entities.json`（或 `_toutiao.json`）、`api/<round>_downloads.json`（含 `file/status`）、`api/<round>_decisions.json`、AI 写的 `api/<round>_plan.json`（每实体 `entityType/region/articleAngle/articleTitle/imageAngle/imageTitle/videoAngle/videoTitle`、可选 `discoverySignals`）。输出 `round.json` 与 `ingest.<carrier>.json`。

```python
E = {e["name"]: e for e in json.load(open(f"{WS}/api/{ROUND}_entities.json"))}
D = json.load(open(f"{WS}/api/{ROUND}_downloads.json")); DEC = json.load(open(f"{WS}/api/{ROUND}_decisions.json")); P = json.load(open(f"{WS}/api/{ROUND}_plan.json"))
DAY = time.strftime("%Y%m%d"); EX = {c: f"{DAY}--travel-{c}-six-step-m1000--national-{ROUND}--pilot-001" for c in ("homepage", "article", "image", "video")}
def media_row(r, kind, relevance, dec):
    row = {"kind": kind, "sourceUrl": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_")) if r["url"].startswith("https://upload.wikimedia.org") else r.get("pageUrl", r["url"]),
           "directUrl": r["url"].split("?")[0], "filePath": r["file"], "license": r["license"], "licenseUrl": r["licenseUrl"], "creator": r.get("artist") or r.get("creator") or "未署名", "description": (r.get("description") or r["title"])[:200],
           "relevance": relevance, "watermarkStatus": dec.get("watermarkStatus", "unknown"), "watermarkKind": dec.get("watermarkKind", "unknown")}
    if r.get("sha1"): row["sha1"] = r["sha1"]
    if dec.get("watermarkNote"): row["watermarkNote"] = dec["watermarkNote"]
    if kind == "video": row["hasAudio"] = bool(dec.get("hasAudio", True))
    if r.get("discoverySignals"): row["discoverySignals"] = r["discoverySignals"]
    return row
def page_row(name, relevance):
    e = E[name]; row = {"kind": "page", "sourceUrl": e["url"], "title": e["title"], "sourceMarkdownPath": f"{WS}/sources/{name}.source.md", "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "creator": f"{e['title']}条目贡献者", "revisionId": e["revid"], "relevance": relevance}
    if P[name].get("discoverySignals"): row["discoverySignals"] = P[name]["discoverySignals"]
    return row
ok = {}
for i, r in enumerate([*D["images"], *D.get("videos", [])]):
    dec = DEC.get(str(i)) or {}
    if r.get("status") == "ok" and dec.get("use"): ok.setdefault((r["entity"], r["role"]), []).append((r, dec))
targets, ingest = [], {c: [] for c in EX}
for name, p in P.items():
    if name not in E: print("SKIP", name, "no source"); continue
    cover = ok.get((name, "homepage_cover"), []); fig = ok.get((name, "article_figure"), []); work = ok.get((name, "image_work"), []); vid = ok.get((name, "video"), [])
    targets.append({"carrier": "homepage", "entityType": p["entityType"], "name": name, "region": p["region"]})
    ingest["homepage"].append({"targetRef": f"entities/{p['entityType']}/{name}", "sources": [page_row(name, "实体条目，事实来源")] + [media_row(r, "image", "主页封面：" + d.get("relevance", "实体主体"), d) for r, d in cover[:1]]})
    if p.get("articleTitle"):
        targets.append({"carrier": "article", "entityType": p["entityType"], "name": name, "publishAngle": p["articleAngle"], "publishTitle": p["articleTitle"]})
        ingest["article"].append({"targetRef": f"posts/article/{p['articleAngle']}/{p['articleTitle']}/1", "sources": [page_row(name, "文章事实参考（factual_reference_only）")] + [media_row(r, "image", "文章配图：" + d.get("relevance", ""), d) for r, d in (fig or cover)[:2]]})
    for k, (r, d) in enumerate(work[:2]):
        title = p["imageTitle"] if k == 0 else p.get("imageTitle2") or f"{p['imageTitle']}（二）"
        targets.append({"carrier": "image", "entityType": p["entityType"], "name": name, "publishAngle": p["imageAngle"], "publishTitle": title})
        ingest["image"].append({"targetRef": f"posts/image/{p['imageAngle']}/{title}/1", "sources": [media_row(r, "image", "图片作品本体：主会话已目视，" + d.get("relevance", "主体切题"), d)]})
    for r, d in vid[:1]:
        targets.append({"carrier": "video", "entityType": p["entityType"], "name": name, "publishAngle": p["videoAngle"], "publishTitle": p["videoTitle"]})
        ingest["video"].append({"targetRef": f"posts/video/{p['videoAngle']}/{p['videoTitle']}/1", "sources": [media_row(r, "video", f"{name} 实景视频", d)]})
used = {c for c in EX if ingest[c]}
json.dump({"schema": "quwoquan_data.round_spec", "executions": {c: EX[c] for c in used}, "targets": targets}, open(f"{WS}/round.json", "w"), ensure_ascii=False, indent=1)
for c in used: json.dump({"schema": "quwoquan_data.ingest_manifest", "executionId": EX[c], "targets": ingest[c]}, open(f"{WS}/ingest.{c}.json", "w"), ensure_ascii=False, indent=1)
print({c: len(ingest[c]) for c in used})
```

随后：`task init --round $QWQ_WS/round.json`；每 carrier `task acquire --execution-id <id> --input $QWQ_WS/ingest.<c>.json`（video 用工具级后台）；`task seal --stage 1.download --input $QWQ_WS/seal.main.json`（`{"actor":{...主会话...},"verdict":"pass"}`）。

## 8. `prompts.py` — 派发清单

从 execution 根读 `0.plan/target_set.json` 与各对象 `1.download/source_refs.json`、`sources/<unit>/assets/index.json`，为 author 生成 `prompt.<carrier>.objects.md`（对象目录绝对路径、来源 `source.md` 路径、可引用资产文件名、原件预览路径、region/entityType/角度/标题），与固定的 `prompt.author.common.md`、`prompt.reviewer.common.md`（正文见 [rounds.md](rounds.md) 派发段；tagRefs 闭集从 `control_plane/governance/taxonomy/_taxonomy.json` 抽 `Entity/地点/*`、`Topic/旅行/玩法/*`、`Topic/自然风光/*`、`Topic/历史文化/*` 叶子）。

```python
import glob
REPO = os.environ["REPO"]; TASKS = f"{REPO}/.qwq_output/data/tasks"
R = json.load(open(f"{WS}/round.json")); D = {r["file"]: r for k in ("images", "videos") for r in json.load(open(f"{WS}/api/{ROUND}_downloads.json")).get(k, []) if r.get("file")}
for carrier, ex in R["executions"].items():
    root = f"{TASKS}/{ex}"; ts = json.load(open(f"{root}/0.plan/target_set.json")); lines = [f"# {carrier} 对象清单（execution 根：{root}）\n"]
    for ref, t in zip(ts["targetRefs"], ts["targets"]):
        refs_p = f"{root}/{ref}/1.download/source_refs.json"
        if not os.path.exists(refs_p): lines.append(f"## {ref}\n- （acquire 未成功，跳过）\n"); continue
        refs = json.load(open(refs_p)); lines.append(f"## {ref}\n- 对象目录：{root}/{ref}\n- 实体：{t['name']} / {t.get('entityType')} / region {t.get('region', '-')} / 角度 {t.get('publishAngle', '-')} / 标题 {t.get('publishTitle', '-')}")
        for s in refs["sources"]:
            unit = f"{root}/" + s["metaRef"].rsplit("/", 1)[0]; meta = json.load(open(f"{unit}/meta.json"))
            if os.path.exists(f"{unit}/source.md") and meta.get("sourceClass") in ("encyclopedia", "web_page"): lines.append(f"- 来源正文：{unit}/source.md（{meta['sourceClass']}）")
            idx = f"{unit}/assets/index.json"
            if os.path.exists(idx):
                for a in json.load(open(idx))["assets"]:
                    att = a.get("sourceAttribution", {}); tail = urllib.parse.unquote(att.get("originalAssetUrl", "")).rsplit("/", 1)[-1]
                    # 原件预览按「实体名 + 原件文件名片段」在下载清单里找；找不到就指向 downloads/ 目录。
                    preview = next((f for f in D if t["name"] in f and slug(os.path.splitext(tail)[0])[:24] in f), f"{WS}/downloads/")
                    lines.append(f"- 资产：assets/{a['fileName']}（{a['mimeType']} {a.get('width')}x{a.get('height')}；作者 {att.get('author', '?')}；{att.get('license', '?')}）；原件预览：{preview}")
        lines.append("")
    open(f"{WS}/prompt.{carrier}.objects.md", "w").write("\n".join(lines)); print(carrier, len(ts["targetRefs"]), "对象")
```

派发：author 子 Agent 提示词 = `prompt.author.common.md` + `prompt.<carrier>.objects.md` 全文；**2+2 错峰**（先 homepage+article，两者返回后再 image+video；image 载体的 `image_work.json` 可由主会话自己写，省一个子 Agent 位）。子 Agent 返回后主会话按其 agentId 写 `seal.author.<carrier>.json`（`sessionId=cursor-subagent-<agentId>`、`runId=run-<agentId>`）并 `task seal --stage 4.draft`。

## 9. `seal_review.py` — 注入 reviewer actor 并封装 5.review

reviewer 子 Agent 只写 `{"verdict","reviews"}` 到 `$QWQ_WS/review.<carrier>.json`；主会话：

```python
carrier, agent_id = sys.argv[1], sys.argv[2]; R = json.load(open(f"{WS}/round.json"))
rev = json.load(open(f"{WS}/review.{carrier}.json"))
rev["actor"] = {"host": "cursor", "modelFamily": "claude", "sessionId": f"cursor-subagent-{agent_id}", "invocation": {"provider": "anthropic", "model": os.environ.get("QWQ_MODEL", "claude-opus-4.1"), "runId": f"run-{agent_id}"}}
out = f"{WS}/seal.review.{carrier}.json"; json.dump(rev, open(out, "w"), ensure_ascii=False, indent=1)
os.execvp("python3", ["python3", f"{os.environ['REPO']}/quwoquan_data/scripts/cli.py", "task", "seal", "--execution-id", R["executions"][carrier], "--stage", "5.review", "--input", out])
```

## 10. `publish.py` — 发布循环（homepage 先于 post）+ 计数

```python
import subprocess
REPO = os.environ["REPO"]; R = json.load(open(f"{WS}/round.json")); TASKS = f"{REPO}/.qwq_output/data/tasks"; results = []
order = [c for c in ("homepage", "article", "image", "video") if c in R["executions"]]
for carrier in order:
    ex = R["executions"][carrier]; rc = f"{TASKS}/{ex}/_shared/receipts/003-5.review.json"
    if not os.path.exists(rc): print("NO REVIEW RECEIPT", carrier); continue
    for item in json.load(open(rc))["resultRefs"]:
        # 003 receipt 的 resultRefs 是 {digest, ref, scope}，ref 指向 .../5.review/content_review.json
        ref = (item["ref"] if isinstance(item, dict) else str(item)).split("/5.review/")[0]
        review = json.load(open(f"{TASKS}/{ex}/{ref}/5.review/content_review.json"))
        if review.get("decision") != "approved": results.append((carrier, ref, "skipped:" + review.get("decision", "?"))); continue
        r = subprocess.run(["python3", f"{REPO}/quwoquan_data/scripts/cli.py", "release", "publish-object", "--execution-id", ex, "--target-ref", ref], capture_output=True, text=True)
        code = re.search(r"DATA\.[A-Z_.]+", r.stdout + r.stderr); results.append((carrier, ref, "published" if r.returncode == 0 else f"fail:{code.group(0) if code else r.returncode}")); print(results[-1])
dump(f"{ROUND}_publish.json", results)
subprocess.run(["python3", f"{REPO}/quwoquan_data/scripts/cli.py", "release", "pool-query", "--json", f"{WS}/pool.after.json"])
```

发布后：`content(data)` 提交 `quwoquan_data/publish/**`（见 [rounds.md](rounds.md)），`rsync -a ~/.local/share/quwoquan/golden_media/ ~/Backups/quwoquan_golden_media/`，然后删除 `$QWQ_WS/downloads/`（原件已进 content library；预览图可留）。

## 集合差（实体名，不是维基标题）

```text
python3 quwoquan_data/scripts/cli.py release pool-query --json /tmp/pool.json
jq -r '[.eligible.homepages[], (.excluded[] | .objectRef | select(startswith("entities/")))] | unique[] | split("/")[-1]' /tmp/pool.json | sort > /tmp/pool_entities.txt
```

候选实体名不在 `/tmp/pool_entities.txt` 才可 init；被 `excluded` 的实体也算「已存在」（重发会 `canonical object drift`）。
