"""显式有界的单条/频道元数据；不合并下载、不把上传账号当作原作者。"""
import hashlib
import json
import subprocess
import inputs
from urllib.parse import urlsplit


def fetch(request, client, hosts):
    url = request["url"]
    if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in hosts:
        raise ValueError("来源必须是该平台的公开 HTTPS 页面")
    mode, limit = request.get("mode"), request.get("limit")
    if mode not in {"single", "channel"} or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("yt-dlp request 必须声明 mode=single|channel 与 1..100 的 limit")
    if mode == "single" and limit != 1:
        raise ValueError("单条模式 limit 必须为 1")
    flags = ["--no-playlist"] if mode == "single" else ["--yes-playlist", "--flat-playlist"]
    command = ["yt-dlp", "--ignore-config", "--skip-download", "--dump-single-json", *flags,
               "--playlist-end", str(limit), "--max-downloads", str(limit),
               "--socket-timeout", "30", "--retries", "0", "--extractor-retries", "0",
               "--user-agent", client.user_agent, "--", url]
    result = subprocess.run(command, capture_output=True, check=False, timeout=120)
    if result.returncode:
        # stdout 若已取得响应也交回 source 先留存，不以失败进程签发成功候选。
        raise inputs.io.TransferError(f"yt-dlp 元数据取得失败（exit={result.returncode}）：{result.stderr.decode(errors='replace')[:400]}", code="SOURCE.YTDLP_FAILED", body=result.stdout)
    return result.stdout


def entries(data):
    if not isinstance(data, dict):
        raise ValueError("yt-dlp 顶层必须是 JSON 对象")
    if "entries" not in data:
        if data.get("_type") in {"playlist", "multi_video"}:
            raise ValueError("yt-dlp 列表响应缺 entries")
        return [data]
    value = data["entries"]
    if value is None or not isinstance(value, list):
        raise ValueError("yt-dlp entries 必须是数组，null 不是空列表或单条成功")
    if any(row is not None and not isinstance(row, dict) for row in value):
        raise ValueError("yt-dlp entries 只支持对象与不可用条目的 null 占位")
    return value


def video_asset(raw, identifier):
    asset = {"id": identifier + ":video"}
    for field in ("width", "height", "duration"):
        if raw.get(field) is not None:
            asset[field] = raw[field]
    size = raw.get("filesize") or raw.get("filesize_approx")
    if size is not None:
        asset["bytes"] = int(size)
    direct = raw.get("url")
    if direct and direct.startswith("https://") and not raw.get("requested_formats") and raw.get("_type") not in {"url", "url_transparent"}:
        asset["directUrl"] = direct
    if str(raw.get("thumbnail", "")).startswith("https://"):
        asset["previewUrl"] = raw["thumbnail"]
    return asset


def video_row(raw, request, source):
    webpage = raw.get("webpage_url") or raw.get("original_url")
    if not webpage and raw.get("_type") in {"url", "url_transparent"}:
        webpage = raw.get("url")
    url = webpage or request["url"]
    identifier = f"{source}:" + str(raw.get("id") or hashlib.sha256(url.encode()).hexdigest()[:24])
    row = {"id": identifier, "kind": "video", "source": source, "sourceUrl": url, "title": raw.get("title") or ""}
    for source_key, target in (("uploader", "uploader"), ("uploader_url", "uploaderUrl"), ("creator", "creator"), ("license", "license"), ("description", "summary")):
        if raw.get(source_key):
            row[target] = raw[source_key]
    row["assets"] = [video_asset(raw, identifier)]
    signals = {key: raw[key] for key in ("view_count", "like_count", "comment_count") if isinstance(raw.get(key), (int, float))}
    if signals:
        row["discoverySignals"] = signals
    return row


def parse(body, request, source):
    data = json.loads(body)
    values = entries(data)
    limit = request.get("limit")
    if "entries" in data and limit is None:
        raise ValueError("yt-dlp entries 回放也必须显式声明 limit")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 100 or len(values) > limit):
        raise ValueError("yt-dlp 响应条数超过显式 limit，或 limit 非法")
    # null 代表该位置不可用，仍计入上限；不伪造候选，也不继续补足更多条目。
    return [video_row(raw, request, source) for raw in values if raw is not None], {}
