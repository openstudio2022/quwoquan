"""显式候选/选择到现有 CLI 输入；不调用 CLI、不选择对象、不写 verdict。"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[2]


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


io = module(SKILL / "scripts/io.py", "content_production_io")


def load(carrier: str, source: str | None = None):
    for value in (carrier, source):
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise io.InputError("载体/来源名必须是模块名，不能是路径")
    relative = f"carriers/{carrier}/sources/{source}.py" if source else f"carriers/{carrier}/adapter.py"
    path = io.safe_path(SKILL, relative)
    if not path.is_file():
        raise io.InputError(f"未实现的载体或来源：{carrier}/{source or 'adapter'}")
    return module(path, f"content_production_{carrier}_{source or 'adapter'}")


def validate(document, schema_path: Path, definition: str | None = None) -> None:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    common_path = SKILL / "schemas/common.schema.json"
    common = io.read_json(common_path)
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    schema = io.read_json(schema_path)
    # 本地注册 Data 唯一 schema 及其相对引用，不出网或复制字段闭集。
    for relative, name in (("source/ingest_manifest.schema.json", "ingest"),
                           ("execution/round_spec.schema.json", "round_spec.schema.json"),
                           ("execution/target_set.schema.json", "target_set.schema.json")):
        path = REPO / "quwoquan_data/schema" / relative
        schema_id = "https://quwoquan.local/content-production/" + name
        data_schema = {**io.read_json(path), "$id": schema_id}
        registry = registry.with_resource(schema_id, Resource.from_contents(data_schema))
        if schema_path == path:
            schema = data_schema
    if definition:
        schema = {"$ref": common["$id"] + "#/$defs/" + definition}
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(document), key=lambda error: str(error.path))
    if errors:
        raise io.InputError("; ".join(f"{list(e.path)}: {e.message}" for e in errors))


def download_index(root, carrier):
    path = io.carrier_path(root, carrier, f"{carrier}/downloads/index.json")
    index = io.read_json(path) if path.exists() else {}
    validate(index, SKILL / "schemas/common.schema.json", "downloads")
    for row in index.values():
        io.carrier_path(root, carrier, row["path"])
        if row.get("metadataPath"):
            io.carrier_path(root, carrier, row["metadataPath"])
    return index


def data_import_path():
    scripts = str(REPO / "quwoquan_data/scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def image_probe(path):
    # 直接复用 Data 唯一像素政策与探测，不在 Skill 复制尺寸/解码准入算法。
    data_import_path()
    from core.image_decode import probe_image_path
    return probe_image_path(path)


def candidate_paths(row, root, carrier):
    if row.get("evidence"):
        io.carrier_path(root, carrier, row["evidence"]["responsePath"])
    if row.get("sourceMarkdownPath"):
        io.carrier_path(root, carrier, row["sourceMarkdownPath"])


def merge_candidate(result, row):
    validate(row, SKILL / "schemas/common.schema.json", "candidate")
    asset_ids = [asset["id"] for asset in row.get("assets", [])]
    if len(asset_ids) != len(set(asset_ids)):
        raise io.InputError(f"候选内资产身份重复：{row['id']}")
    prior = result.get(row["id"])
    if prior is None:
        result[row["id"]] = row
        return
    before = {k: v for k, v in prior.items() if k != "evidence"}
    after = {k: v for k, v in row.items() if k != "evidence"}
    if before != after:
        raise io.InputError(f"候选身份内容冲突：{row['id']}")


def candidates(paths: list[Path], root=None, carrier=None) -> dict:
    result = {}
    for path in paths:
        rows = io.read_json(path)
        if not isinstance(rows, list):
            raise io.InputError("候选快照必须是数组")
        for row in rows:
            merge_candidate(result, row)
            if root is not None:
                candidate_paths(row, root, carrier)
    return result


def register_local(root, pool, args):
    candidate = pool[args.candidate_id]
    assets = {asset["id"]: asset for asset in candidate.get("assets", [])}
    asset = assets[args.asset_id]
    candidate_paths(candidate, root, args.carrier)
    media = io.carrier_path(root, args.carrier, args.file)
    metadata_path = io.carrier_path(root, args.carrier, args.metadata)
    metadata = io.read_json(metadata_path)
    expected_id = candidate["id"].split(":", 1)[1]
    if candidate["source"] not in {"youtube", "bilibili"} or str(metadata.get("id")) != expected_id or metadata.get("webpage_url") != candidate["sourceUrl"]:
        raise io.InputError("yt-dlp 本地元数据与候选身份不一致")
    if media.stat().st_size > args.max_bytes or args.max_bytes <= 0:
        raise io.InputError("本地结果超过显式登记预算")
    facts = io.file_hashes(media)
    if not facts["bytes"] or facts["bytes"] > args.max_bytes:
        raise io.InputError("yt-dlp 本地结果为空或读取期间超过预算")
    if asset.get("sha1") and asset["sha1"].lower() != facts["sha1"]:
        raise io.InputError("yt-dlp 本地结果来源 sha1 不符")
    # 没有单文件直链时只登记本地取得事实，不把 watch 页面冒充 directUrl。
    row = {"path": args.file, "sha256": facts["sha256"], "bytes": facts["bytes"], "acquisition": "ytdlp_local",
           "sourceUrl": candidate["sourceUrl"], "metadataPath": args.metadata, "metadataSha256": io.file_hashes(metadata_path)["sha256"]}
    if asset.get("directUrl"):
        row["directUrl"] = asset["directUrl"]
    index = download_index(root, args.carrier)
    if args.asset_id in index and index[args.asset_id] != row:
        raise io.InputError("本地结果登记身份冲突")
    index[args.asset_id] = row
    validate(index, SKILL / "schemas/common.schema.json", "downloads")
    io.write(io.carrier_path(root, args.carrier, f"{args.carrier}/downloads/index.json"), io.encode(index), replace=True)
    return {"registered": args.asset_id, "sha256": facts["sha256"], "bytes": facts["bytes"], "metadataSha256": row["metadataSha256"]}


def execution_target_ref(target: dict) -> str:
    """ingest/receipt 使用的过程 locator；路径算法只由 Data 拥有。"""
    validate(target, SKILL / "schemas/common.schema.json", "target")
    data_import_path()
    from content.execution.task_init import execution_target_ref as data_execution_target_ref
    frozen = dict(target)
    if target["carrier"] != "homepage":
        frozen.setdefault("publishSeq", 1)
    return data_execution_target_ref(frozen, carrier=target["carrier"])


def canonical_target_ref(target: dict) -> str:
    """池查询使用逻辑身份，homepage 不借用 execution hash 目录。"""
    validate(target, SKILL / "schemas/common.schema.json", "target")
    if target["carrier"] == "homepage":
        return "entities/" + target["entityRef"].removeprefix("/entity/")
    return execution_target_ref(target)


def verify_fact(evidence, root, carrier):
    path = io.carrier_path(root, carrier, evidence["responsePath"])
    body = path.read_bytes()
    if io.digest(body) != evidence["responseSha256"]:
        raise io.InputError("纠正证据摘要漂移")
    if evidence["quote"].encode() not in body:
        raise io.InputError("纠正证据 quote 不在原文中")


def rights_facts(original, selected, root, carrier):
    result = {key: original[key] for key in ("license", "licenseUrl", "creator") if key in original}
    for field in ("license", "licenseUrl", "creator"):
        if field not in selected:
            continue
        before, after = original.get(field), selected[field]
        secure_same = field == "licenseUrl" and before and before.startswith("http://") and after == "https://" + before[7:]
        evidence = selected.get("factEvidence", {}).get(field)
        if before is not None and before != after and not secure_same and not evidence:
            raise io.InputError(f"选择不能改写来源事实，纠正须精确证据：{field}")
        if evidence:
            verify_fact(evidence, root, carrier)
        result[field] = after
    return result


def source_facts(candidate, choice, root, carrier):
    candidate_paths(candidate, root, carrier)
    evidence = candidate.get("evidence")
    if evidence:
        response = io.carrier_path(root, carrier, evidence["responsePath"])
        if io.digest(response.read_bytes()) != evidence["responseSha256"]:
            raise io.InputError(f"原始响应摘要漂移：{candidate['id']}")
    if "accessPolicy" in candidate and "accessPolicy" in choice and candidate["accessPolicy"] != choice["accessPolicy"]:
        raise io.InputError("选择不能改写来源访问事实")
    base = {"sourceUrl": candidate["sourceUrl"], "relevance": choice["relevance"], **rights_facts(candidate, choice, root, carrier)}
    for field in ("accessPolicy", "discoverySignals"):
        value = choice.get(field, candidate.get(field))
        if value is not None:
            base[field] = value
    return base


def page_row(root, carrier, candidate, base):
    page_path = io.carrier_path(root, carrier, candidate["sourceMarkdownPath"])
    if not page_path.is_file():
        raise io.InputError(f"来源底稿缺失：{page_path}")
    if candidate.get("sourceMarkdownSha256") and io.digest(page_path.read_bytes()) != candidate["sourceMarkdownSha256"]:
        raise io.InputError(f"来源底稿摘要漂移：{page_path}")
    return {**base, "kind": "page", "title": candidate["title"], "sourceMarkdownPath": str(page_path)}


def selected_assets(candidate, choice):
    raw_assets = candidate.get("assets", [])
    assets = {asset["id"]: asset for asset in raw_assets}
    if len(assets) != len(raw_assets):
        raise io.InputError("候选资产身份重复")
    selected_ids = [selected["id"] for selected in choice.get("assets", [])]
    if not selected_ids or len(selected_ids) != len(set(selected_ids)) or not set(selected_ids) <= set(assets):
        raise io.InputError("选中媒体须有已取得直链且资产引用唯一")
    return [(assets[selected["id"]], selected) for selected in choice["assets"]]


def media_row(root, carrier, candidate, base, asset, selected, local):
    path = io.cached_file(root, carrier, {**asset, "sourceUrl": candidate["sourceUrl"]}, local)
    rights = rights_facts({**base, **asset}, selected, root, carrier)
    if not local.get("directUrl"):
        raise io.InputError("SOURCE.DIRECT_URL_REQUIRED：本地结果已登记，但当前 Data ingest 要求实际单文件 directUrl；不得用作品页冒充")
    row = {**base, **rights, "kind": candidate["kind"], "directUrl": local["directUrl"], "filePath": str(path)}
    for field in ("sha1", "description"):
        if asset.get(field) is not None:
            row[field] = asset[field]
    for field in ("watermarkStatus", "watermarkKind", "watermarkNote", "hasAudio", "commercialAuthorizationStatus",
                  "authorizationProof", "audioRightsStatus", "usageScope", "modelReleaseStatus", "propertyReleaseStatus"):
        if field in selected:
            row[field] = selected[field]
    return row


def source_rows(choices: list, pool: dict, downloads: dict, root: Path, carrier: str) -> list:
    result = []
    for choice in choices:
        candidate = pool[choice["candidateId"]]
        base = source_facts(candidate, choice, root, carrier)
        if candidate["kind"] == "page":
            result.append(page_row(root, carrier, candidate, base))
        else:
            for asset, selected in selected_assets(candidate, choice):
                result.append(media_row(root, carrier, candidate, base, asset, selected, downloads[asset["id"]]))
    return result


def carrier_ingest(root, selection, pool, downloads):
    carrier = selection["carrier"]
    adapter = load(carrier)
    validate(selection, SKILL / f"carriers/{carrier}/schemas/selection.schema.json")
    validate(list(pool.values()), SKILL / f"carriers/{carrier}/schemas/candidate.schema.json")
    validate(downloads, SKILL / "schemas/common.schema.json", "downloads")
    for candidate in pool.values():
        candidate_paths(candidate, root, carrier)
    for local in downloads.values():
        io.carrier_path(root, carrier, local["path"])
        if local.get("metadataPath"):
            io.carrier_path(root, carrier, local["metadataPath"])
    targets = []
    for chosen in selection["targets"]:
        adapter.check(chosen, pool)
        if chosen["target"]["carrier"] != carrier:
            raise io.InputError("选择与 target 的 carrier 不一致")
        targets.append({"targetRef": execution_target_ref(chosen["target"]), "sources": source_rows(chosen["sources"], pool, downloads, root, carrier)})
    return {"schema": "quwoquan_data.ingest_manifest", "executionId": selection["executionId"], "targets": targets}


def preflight_input(root, relative):
    parts = Path(relative).parts
    if len(parts) < 2:
        raise io.InputError("预检路径必须显式包含载体和文件：<carrier>/<file>")
    carrier = parts[0]
    path = io.carrier_path(root, carrier, relative)
    load(carrier)
    return carrier, io.read_json(path)


def preflight_selection(root, relative):
    carrier, selection = preflight_input(root, relative)
    validate(selection, SKILL / f"carriers/{carrier}/schemas/selection.schema.json")
    refs, targets = set(), set()
    for chosen in selection["targets"]:
        target = chosen["target"]
        if target["carrier"] != carrier:
            raise io.InputError("预检选择与 target 的 carrier 不一致")
        ref = canonical_target_ref(target)
        targets.add(ref)
        refs.add(ref)
        refs.add("entities/" + target["entityRef"].removeprefix("/entity/"))
    return refs, targets


def preflight_manifest(candidate, carrier):
    if not isinstance(candidate, dict) or set(candidate) != {"objectRef", "manifest"}:
        raise io.InputError("预检候选必须是 {objectRef,manifest}，不是 source candidate 或草稿正文")
    ref, manifest = candidate["objectRef"], candidate["manifest"]
    prefix = "entities/" if carrier == "homepage" else f"posts/{carrier}/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        raise io.InputError("预检候选不得引用另一个载体工作区")
    expected_type = "article" if carrier == "homepage" else carrier
    if not isinstance(manifest, dict) or manifest.get("contentType") != expected_type:
        raise io.InputError("预检 manifest 必须声明当前 contentType")
    if carrier == "homepage":
        expected_ref = "/entity/" + ref.removeprefix("entities/")
        if manifest.get("schema") != "quwoquan_data.entity_object" or manifest.get("entityRef") != expected_ref:
            raise io.InputError("主页预检须使用 Data entity manifest 与精确 entityRef")
    elif not isinstance(manifest.get("entityRefs"), list):
        raise io.InputError("预检 manifest 必须显式声明 entityRefs，不能把缺席当空集合")
    if not isinstance(manifest.get("assets"), list):
        raise io.InputError("预检 manifest 必须显式声明 assets，不能把缺席当空集合")
    for asset in manifest["assets"]:
        preflight_asset(asset, carrier)
    return ref


def preflight_asset(asset, carrier):
    if not isinstance(asset, dict) or not asset.get("assetId") or not asset.get("sha256"):
        raise io.InputError("预检资产缺 Data 取得的 assetId/sha256")
    image = carrier == "image" or asset.get("kind") == "image" or str(asset.get("mimeType", "")).startswith("image/")
    if image and not asset.get("perceptualHash"):
        raise io.InputError("SOURCE.PREFLIGHT_IMAGE_FACTS_REQUIRED：图片预检须有 Data 资产 pHash，不得填占位值或调用发布投影")


def preflight_candidates(root, relatives):
    candidates, seen = [], set()
    for relative in relatives:
        carrier, document = preflight_input(root, relative)
        if not isinstance(document, dict) or not isinstance(document.get("candidates"), list) or not document["candidates"]:
            raise io.InputError("预检输入须是非空 {candidates:[{objectRef,manifest}]}；空输入不得触发全池查询")
        for candidate in document["candidates"]:
            ref = preflight_manifest(candidate, carrier)
            if ref in seen:
                raise io.InputError(f"预检候选身份重复：{ref}")
            seen.add(ref)
            candidates.append(candidate)
    return candidates


def acquired_candidates(root, relative):
    carrier, document = preflight_input(root, relative)
    validate(document, SKILL / "schemas/common.schema.json", "acquiredSelection")
    prefix = "entities/" if carrier == "homepage" else f"posts/{carrier}/"
    if any(not row["objectRef"].startswith(prefix) for row in document["targets"]):
        raise io.InputError("取得资产选择不得引用另一个载体；在读取 execution 前拒绝")
    data_import_path()
    from content.release.canonical.image_identity import acquired_asset_identity_view
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    from core.paths import execution_root
    try:
        candidates = acquired_asset_identity_view(
            execution_root=execution_root(document["executionId"]), selections=document["targets"], carrier=carrier,
        )
    except ObjectTransactionError as error:
        raise io.InputError(str(error)) from error
    for candidate in candidates:
        preflight_manifest(candidate, carrier)
    return candidates


def preflight(root, args):
    refs, selected = set(args.target_ref), set()
    for relative in args.selection:
        dependencies, targets = preflight_selection(root, relative)
        refs.update(dependencies)
        selected.update(targets)
    candidates = preflight_candidates(root, args.candidate_file)
    for relative in args.acquired_selection:
        candidates.extend(acquired_candidates(root, relative))
    candidate_refs = [candidate["objectRef"] for candidate in candidates]
    if len(candidate_refs) != len(set(candidate_refs)):
        raise io.InputError("预检候选身份重复：同一对象不能同时提交多份资产视图")
    if not refs and not candidates:
        raise io.InputError("预检必须显式点名 selection、acquired-selection、candidate-file 或 target-ref；不隐式扫描全池")
    data_import_path()
    from content.release.canonical.pool_query import query_pool
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    from core.paths import PUBLISH_ROOT
    # Data 唯一 reader 内只打开一次图片索引，跨候选冲突也在同一批检查。
    try:
        result = query_pool(args.publish_root or PUBLISH_ROOT, target_refs=sorted(refs), candidates=candidates)
    except ObjectTransactionError as error:
        raise io.InputError(str(error)) from error
    checked = sorted(candidate["objectRef"] for candidate in candidates)
    return {"poolQuery": result, "coverage": {"candidateManifestRefs": checked,
            "identityOnlyTargetRefs": sorted((refs | selected) - set(checked)),
            "selectedWithoutManifestRefs": sorted(selected - set(checked))}}


def validate_outputs(round_doc, ingests):
    # 复用 Data authoring schema，而不是复制 wire 字段闭集。
    validate(round_doc, REPO / "quwoquan_data/schema/execution/round_spec.schema.json")
    refs = [execution_target_ref(target) for target in round_doc["targets"]]
    for ref in refs:
        if any(part in {"", ".", ".."} for part in ref.split("/")) or "\\" in ref:
            raise io.InputError("对象身份包含非法路径段")
    if len(refs) != len(set(refs)):
        raise io.InputError("同轮 target 身份重复")
    for document in ingests.values():
        validate(document, REPO / "quwoquan_data/schema/source/ingest_manifest.schema.json")


def build(root: Path, selections: list[dict], pool: dict, downloads: dict) -> dict:
    round_doc = {"schema": "quwoquan_data.round_spec", "executions": {}, "targets": []}
    ingests = {}
    for selection in selections:
        carrier = selection["carrier"]
        if carrier in ingests:
            raise io.InputError(f"一轮每载体仅一份选择：{carrier}")
        ingests[carrier] = carrier_ingest(root, selection, pool[carrier], downloads.get(carrier, {}))
        round_doc["targets"].extend(chosen["target"] for chosen in selection["targets"])
        round_doc["executions"][carrier] = selection["executionId"]
        if selection.get("retryOf"):
            round_doc.setdefault("retryOf", {})[carrier] = selection["retryOf"]
    validate_outputs(round_doc, ingests)
    return {"round.json": round_doc, **{f"{carrier}/ingest.json": doc for carrier, doc in ingests.items()}}
