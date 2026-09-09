"""宿主点名的单阶段工具；不派 Agent、不 seal、不 publish、不决定后继。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import inputs

io = inputs.io


def download_tasks(pool, selections):
    for selection in selections:
        carrier = selection["carrier"]
        adapter = inputs.load(carrier)
        inputs.validate(selection, inputs.SKILL / f"carriers/{carrier}/schemas/selection.schema.json")
        for target in selection["targets"]:
            adapter.check(target, pool[carrier])
            for choice in target["sources"]:
                candidate = pool[carrier][choice["candidateId"]]
                assets = {asset["id"]: asset for asset in candidate.get("assets", [])}
                for selected in choice.get("assets", []):
                    yield carrier, candidate, assets[selected["id"]]


def unique_download_tasks(pool, selections):
    identities, tasks = {}, []
    for carrier, candidate, asset in download_tasks(pool, selections):
        key = (carrier, asset["id"])
        identity = (candidate["sourceUrl"], asset)
        if key in identities:
            if identities[key] != identity:
                raise io.InputError(f"批内资产身份冲突：{carrier}/{asset['id']}")
            continue
        identities[key] = identity
        tasks.append((carrier, candidate, asset))
    return tasks


def download_asset(root, carrier, candidate, asset, fetch, budget, max_bytes):
    url = asset.get("directUrl")
    if not url:
        raise io.TransferError("没有单文件直链，请由宿主 yt-dlp 下载并登记", code="SOURCE.LOCAL_RESULT_REQUIRED")
    expected = asset.get("bytes", 0)
    budget.check(expected)
    if expected > max_bytes:
        raise io.TransferError("申报大小超过单资产预算", code="SOURCE.BUDGET_EXCEEDED")
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".ogv"}:
        suffix = ".bin"
    relative = f"{carrier}/downloads/{io.key(asset['id'])}{suffix}"
    path = io.carrier_path(root, carrier, relative)
    facts = io.store_chunks(path, fetch.chunks(url, max_bytes=min(max_bytes, budget.remaining)), budget, max_bytes, asset.get("sha1"))
    row = {"directUrl": url, "path": relative, **facts}
    if candidate["kind"] == "image":
        probe = inputs.image_probe(path)
        if not probe.succeeded:
            raise io.TransferError(f"图片探测失败：{probe.failure}")
        row.update(width=probe.width, height=probe.height)
    return row


def download(root, pool, selections, fetch, max_bytes, total_bytes=None):
    # 缓存身份/载体损坏是完整性错误，先于任何网络读取失败；普通取得错误逐项汇总。
    if max_bytes <= 0:
        raise io.InputError("单资产传输预算必须为正数")
    tasks = unique_download_tasks(pool, selections)
    indexes = {s["carrier"]: inputs.download_index(root, s["carrier"]) for s in selections}
    for carrier, candidate, asset in tasks:
        inputs.candidate_paths(candidate, root, carrier)
        prior = indexes[carrier].get(asset["id"])
        if prior:
            io.cached_file(root, carrier, {**asset, "sourceUrl": candidate["sourceUrl"]}, prior)
    budget = io.Budget(total_bytes if total_bytes is not None else max_bytes)
    failures, stopped = [], set()
    for carrier, candidate, asset in tasks:
        if asset["id"] in indexes[carrier]:
            io.cached_file(root, carrier, {**asset, "sourceUrl": candidate["sourceUrl"]}, indexes[carrier][asset["id"]])
            continue
        host = io.urllib.parse.urlsplit(asset.get("directUrl", candidate["sourceUrl"])).hostname
        try:
            if host in stopped:
                raise io.TransferError("本次调用已停止该站点", code="SOURCE.SITE_STOPPED")
            row = download_asset(root, carrier, candidate, asset, fetch, budget, max_bytes)
            indexes[carrier][asset["id"]] = row
            io.write(io.carrier_path(root, carrier, f"{carrier}/downloads/index.json"), io.encode(indexes[carrier]), replace=True)
        except (io.TransferError, OSError) as error:
            if getattr(error, "stop_site", False) or getattr(error, "code", None) in {429, 503}:
                stopped.add(host)
            budget.used += len(getattr(error, "body", b""))
            budget.remaining -= len(getattr(error, "body", b""))
            failures.append({"carrier": carrier, "assetId": asset["id"], "code": getattr(error, "code", "SOURCE.ASSET_FAILED"), "message": str(error)})
    if failures:
        raise io.PartialFailure({"downloaded": {c: len(i) for c, i in indexes.items()}, "failures": failures, "transferredBytes": budget.used})
    return indexes


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True, help="该轮根，输入相对路径从此解析")
    p.add_argument("--user-agent", default=os.environ.get("QWQ_SOURCE_USER_AGENT", ""))
    p.add_argument("--gap", type=float, default=1.5)
    commands = p.add_subparsers(dest="action", required=True)
    discover = commands.add_parser("source", help="取得点名来源；可从离线响应回放")
    discover.add_argument("carrier")
    discover.add_argument("source")
    discover.add_argument("--request", required=True, help="显式查询参数 JSON 相对路径")
    discover.add_argument("--response", help="离线 fixture 相对路径；不出网")
    discover.add_argument("--output", required=True)
    for name in ("download", "build-inputs"):
        sub = commands.add_parser(name)
        sub.add_argument("--candidates", nargs="+", required=True)
        sub.add_argument("--selection", nargs="+", required=True)
        if name == "download":
            sub.add_argument("--max-bytes", type=int, required=True, help="单资产传输预算，不是准入阈值")
            sub.add_argument("--total-bytes", type=int, required=True, help="本次调用总传输预算（失败传输也计入）")
    preview = commands.add_parser("preview")
    preview.add_argument("carrier")
    preview.add_argument("--candidates", nargs="+", required=True)
    preview.add_argument("--discovery", action="store_true", help="缺原件时显式取得发现缩略图")
    preview.add_argument("--max-bytes", type=int, help="发现模式总传输预算")
    register = commands.add_parser("register-local", help="机械核验并登记宿主 yt-dlp 本地结果，不下载")
    register.add_argument("carrier", choices=["video"])
    register.add_argument("--candidates", nargs="+", required=True)
    register.add_argument("--candidate-id", required=True)
    register.add_argument("--asset-id", required=True)
    register.add_argument("--file", required=True, help="当前载体下 yt-dlp 本地媒体")
    register.add_argument("--metadata", required=True, help="当前载体下 yt-dlp info.json")
    register.add_argument("--max-bytes", type=int, required=True)
    preflight = commands.add_parser("preflight", help="一次批量调用 Data 只读 pool-query；不选择或批准对象")
    preflight.add_argument("--selection", nargs="+", default=[], help="当前载体 selection；保留显式 entityId/entityRef，检查 canonical 逻辑身份及依赖，不使用 execution locator")
    preflight.add_argument("--acquired-selection", nargs="+", default=[], help="当前载体已取得资产选择：{executionId,targets:[{objectRef,assetRefs}]}；不读草稿")
    preflight.add_argument("--candidate-file", nargs="+", default=[], help="当前载体的 {candidates:[{objectRef,manifest}]} 身份视图")
    preflight.add_argument("--target-ref", action="append", default=[], help="额外点名 canonical 对象，可重复")
    preflight.add_argument("--publish-root", type=Path, help="独立内容仓根；仅只读，缺省 Data QWQ_PUBLISH_ROOT 绑定，不是 execution 工作包路径")
    lint = commands.add_parser("lint")
    lint.add_argument("carrier")
    lint.add_argument("--draft", required=True, help="只读草稿：轮根相对路径或 exact execution 绝对路径")
    return p


def write_snapshot(root, materialized):
    """先检查已知冲突再写；并发同路径最终由 create-or-same 判定。"""
    for relative, payload in materialized.items():
        path = io.safe_path(root, relative)
        if path.exists() and path.read_bytes() != payload:
            raise io.InputError(f"快照不可覆盖：{relative}")
    for relative, payload in materialized.items():
        io.write(io.safe_path(root, relative), payload)


def source_run(args, root):
    source = inputs.load(args.carrier, args.source)
    output = io.safe_path(root, args.output)
    if not output.is_relative_to(root / args.carrier):
        raise io.InputError("来源输出必须放在当前载体目录")
    request = io.read_json(io.carrier_path(root, args.carrier, args.request))
    if not isinstance(request, dict):
        raise io.InputError("来源 request 必须是对象")
    secrets = ("token", "password", "secret", "cookie", "authorization", "api_key")
    if any(any(secret in key.lower() for secret in secrets) for key in request):
        raise io.InputError("凭据只允许本机环境，不得写入来源 request")
    try:
        body = io.carrier_path(root, args.carrier, args.response).read_bytes() if args.response else source.fetch(request, io.Fetcher(args.user_agent, args.gap))
    except io.TransferError as error:
        if error.body:
            relative = preserve_response(root, args.carrier, error.body)
            raise io.InputError(f"{error.code}: {error}; responsePath={relative}; responseSha256={io.digest(error.body)}; responseComplete=false（保留已读前缀）") from error
        raise
    response_path = preserve_response(root, args.carrier, body)
    try:
        rows, texts = source.parse(body, request)
        for row in rows:
            if row.get("sourceMarkdownPath"):
                row["sourceMarkdownSha256"] = io.digest(texts[row["sourceMarkdownPath"]].encode())
                row["sourceMarkdownPath"] = f"{args.carrier}/" + row["sourceMarkdownPath"]
            row["evidence"] = {"responsePath": response_path, "responseSha256": io.digest(body), "request": request}
        inputs.validate(rows, inputs.SKILL / f"carriers/{args.carrier}/schemas/candidate.schema.json")
        materialized = {f"{args.carrier}/{relative}": text.encode() for relative, text in texts.items()}
        for relative in materialized:
            io.carrier_path(root, args.carrier, relative)
        write_snapshot(root, {**materialized, args.output: io.encode(rows)})
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise io.InputError(f"SOURCE.RESPONSE_INVALID {args.source}: {error}; responsePath={response_path}; responseSha256={io.digest(body)}") from error
    result = {"candidates": len(rows), "output": args.output, "responsePath": response_path, "responseSha256": io.digest(body)}
    if args.source == "commons":
        result["continue"] = json.loads(body).get("continue")
    return result


def preserve_response(root, carrier, body):
    relative = f"{carrier}/sources/responses/{io.digest(body)}.raw"
    io.write(io.carrier_path(root, carrier, relative), body)
    return relative


def load_pool(args, root):
    paths = {}
    for relative in args.candidates:
        owner = Path(relative).parts[0]
        if getattr(args, "carrier", owner) != owner:
            raise io.InputError("候选文件不得引用另一个载体工作区")
        inputs.load(owner)
        paths.setdefault(owner, []).append(io.carrier_path(root, owner, relative))
    return {carrier: inputs.candidates(files, root, carrier) for carrier, files in paths.items()}


def preview_run(args, root, pool):
    import preview
    inputs.load(args.carrier)
    fetch = io.Fetcher(args.user_agent, args.gap) if args.discovery else None
    assets = [{**asset, "workId": row["id"]} for row in pool[args.carrier].values() for asset in row.get("assets", [])]
    return {"previews": preview.make(root, args.carrier, assets, fetch, discovery=args.discovery, max_bytes=args.max_bytes)}


def selection_run(args, root, pool):
    selections = []
    for relative in args.selection:
        carrier = Path(relative).parts[0]
        inputs.load(carrier)
        selection = io.read_json(io.carrier_path(root, carrier, relative))
        if carrier != selection["carrier"]:
            raise io.InputError("选择文件必须放在所属载体目录")
        selections.append(selection)
    if args.action == "download":
        indexes = download(root, pool, selections, io.Fetcher(args.user_agent, args.gap), args.max_bytes, args.total_bytes)
        return {"downloaded": {carrier: len(index) for carrier, index in indexes.items()}}
    downloads = {selection["carrier"]: inputs.download_index(root, selection["carrier"]) for selection in selections}
    outputs = inputs.build(root, selections, pool, downloads)
    write_snapshot(root, {relative: io.encode(document) for relative, document in outputs.items()})
    return {"outputs": list(outputs)}


def run(args):
    root = args.workspace.absolute()
    if args.action == "source":
        return source_run(args, root)
    if args.action == "preflight":
        return inputs.preflight(root, args)
    if args.action == "lint":
        # lint 只读，允许 exact execution 产物；不为检查复制第二份草稿。
        draft = Path(args.draft)
        path = io.safe_path(draft.parent, draft.name) if draft.is_absolute() else io.safe_path(root, args.draft)
        if not path.is_file():
            raise io.InputError("lint 输入必须是普通草稿文件")
        return {"advisories": inputs.load(args.carrier).lint(path)}
    pool = load_pool(args, root)
    if args.action == "register-local":
        return inputs.register_local(root, pool[args.carrier], args)
    if args.action == "preview":
        return preview_run(args, root, pool)
    return selection_run(args, root, pool)


def main(argv=None):
    try:
        result = run(parser().parse_args(argv))
    except io.PartialFailure as error:
        print(json.dumps({"status": "partial_failure", **error.result}, ensure_ascii=False))
        return 1
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
