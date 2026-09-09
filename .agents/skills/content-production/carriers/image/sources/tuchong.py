"""图虫一次公开响应按 post 分组；不展开为逐图片作品。"""
import json
from urllib.parse import quote


def fetch(request, client):
    if request.get("siteId"):
        base = f"https://tuchong.com/rest/sites/{quote(str(request['siteId']), safe='')}/posts"
    else:
        base = f"https://tuchong.com/rest/tags/{quote(request['tag'], safe='')}/posts"
    return client.get(f"{base}?page={int(request.get('page', 1))}&count=20&order={quote(request.get('order', 'weekly'))}")


def site_index(value):
    if value is None:
        return {}
    if isinstance(value, dict) and all(isinstance(site, dict) for site in value.values()):
        return value
    if isinstance(value, list) and all(isinstance(site, dict) and site.get("site_id") is not None for site in value):
        return {str(site["site_id"]): site for site in value}
    raise ValueError("图虫 siteList 必须是账号字典、含 site_id 的对象数组或 null")


def post_assets(post):
    assets = []
    for image in post.get("images", []):
        asset = {"id": f"tuchong:{image['user_id']}:{image['img_id']}",
                 "directUrl": f"https://photo.tuchong.com/{image['user_id']}/f/{image['img_id']}.jpg",
                 "description": post.get("excerpt") or post.get("title") or ""}
        for field in ("width", "height"):
            if image.get(field):
                asset[field] = image[field]
        assets.append(asset)
    return assets


def post_row(post, site, assets):
    url = post.get("url") or f"https://tuchong.com/{site['site_id']}/{post['post_id']}/"
    identifier = str(post.get("post_id") or url.rstrip("/").rsplit("/", 1)[-1])
    row = {"id": f"tuchong:{identifier}", "kind": "image", "source": "tuchong", "sourceUrl": url,
           "title": post.get("title") or "", "assets": assets}
    if site.get("name"):
        row["uploader"] = site["name"]
    if site.get("site_id"):
        row["uploaderUrl"] = f"https://tuchong.com/{site['site_id']}/"
    signals = {key: post[key] for key in ("views", "favorites", "comments", "collected") if isinstance(post.get(key), (int, float))}
    if signals:
        row["discoverySignals"] = signals
    return row


def parse(body, request):
    data = json.loads(body)
    sites = site_index(data.get("siteList"))
    rows = []
    for post in data.get("postList", data.get("posts", [])):
        site = post.get("site") or sites.get(str(post.get("author_id", post.get("site_id", ""))), {})
        assets = post_assets(post)
        if assets:
            rows.append(post_row(post, site, assets))
    return rows, {}
