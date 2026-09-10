"""本载体摘要核验原件优先；发现缩略图必须显式开启，分页释放栅格。"""
from __future__ import annotations

from pathlib import Path
import io as byte_io

import inputs

io = inputs.io


def preview_source(root, carrier, asset, downloads, fetch, discovery, budget):
    prior = downloads.get(asset["id"])
    if prior:
        path = io.cached_file(root, carrier, asset, prior)
        return path, prior["sha256"], "original", prior["directUrl"]
    if not discovery:
        raise io.InputError(f"缺少本载体原件；发现模式须显式 --discovery：{asset['id']}")
    url = asset.get("previewUrl") or asset.get("directUrl")
    if not url:
        raise io.InputError(f"没有图片预览地址：{asset['id']}")
    cache = io.carrier_path(root, carrier, f"{carrier}/preview/source-{io.key(asset['id'] + url)}.json")
    if cache.exists():
        row = io.read_json(cache)
        path = io.cached_file(root, carrier, {"id": asset["id"], "directUrl": url}, row)
        return path, row["sha256"], "discovery", url
    budget.check(0)
    body = fetch.get(url, max_bytes=budget.remaining)
    budget.consume(len(body))
    sha256 = io.digest(body)
    relative = f"{carrier}/preview/raw-{sha256}"
    path = io.carrier_path(root, carrier, relative)
    io.write(path, body)
    io.write(cache, io.encode({"path": relative, "directUrl": url, "sha256": sha256, "bytes": len(body)}))
    return path, sha256, "discovery", url


def tile_for(root, carrier, asset, source):
    from PIL import Image, ImageDraw
    path, sha256, origin, url = source
    probe = inputs.image_probe(path)
    from core.image_decode import draft_to_display_width, oriented_raster
    if not probe.succeeded:
        raise io.InputError(f"预览图片探测失败：{probe.failure}")
    relative = f"{carrier}/preview/{io.key(asset['id'] + sha256 + origin)}.jpg"
    output = io.carrier_path(root, carrier, relative)
    if not output.exists():
        with Image.open(path) as image:
            draft_to_display_width(image, probe=probe, target_width=1280)
            with oriented_raster(image) as raster:
                raster.thumbnail((1280, 1280))
                with raster.convert("RGB") as rgb, byte_io.BytesIO() as buffer:
                    rgb.save(buffer, format="JPEG", quality=90)
                    io.write(output, buffer.getvalue())
    tile = Image.new("RGB", (512, 570), "white")
    with Image.open(output) as miniature:
        miniature.thumbnail((512, 512))
        tile.paste(miniature, (0, 0))
    label = io.key(asset["id"])
    ImageDraw.Draw(tile).text((5, 518), f"{label}\n{origin} {probe.width}x{probe.height}", fill="black")
    return tile, {"assetId": asset["id"], "workId": asset.get("workId"), "label": label, "path": relative,
                  "source": origin, "sourceUrl": url, "sourceSha256": sha256, "width": probe.width, "height": probe.height}


def save_sheet(root, carrier, tiles):
    from PIL import Image
    with Image.new("RGB", (1024, 570 * ((len(tiles) + 1) // 2)), "white") as sheet:
        for index, tile in enumerate(tiles):
            sheet.paste(tile, ((index % 2) * 512, (index // 2) * 570))
        with byte_io.BytesIO() as buffer:
            sheet.save(buffer, format="JPEG", quality=85)
            body = buffer.getvalue()
            io.write(io.carrier_path(root, carrier, f"{carrier}/preview/sheet-{io.digest(body)[:24]}.jpg"), body)


def make(root: Path, carrier: str, assets: list[dict], fetch=None, *, discovery=False, max_bytes=None) -> list[str]:
    if not assets:
        return []
    # 在任何下载缓存字节读取之前，先校验整份 index 的载体与 schema。
    downloads = inputs.download_index(root, carrier)
    if discovery and (max_bytes is None or max_bytes <= 0):
        raise io.InputError("发现模式必须声明 --max-bytes 总传输预算")
    budget = io.Budget(max_bytes or 1)
    records = []
    for start in range(0, len(assets), 8):
        tiles = []
        try:
            for asset in assets[start:start + 8]:
                source = preview_source(root, carrier, asset, downloads, fetch, discovery, budget)
                tile, row = tile_for(root, carrier, asset, source)
                tiles.append(tile)
                records.append(row)
            save_sheet(root, carrier, tiles)
        finally:
            for tile in tiles:
                tile.close()
    paths = [row["path"] for row in records]
    io.write(io.carrier_path(root, carrier, f"{carrier}/preview/index-{io.key('|'.join(paths))}.json"), io.encode(records))
    return paths
