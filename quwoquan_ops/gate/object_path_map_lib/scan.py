"""端云物理树扫描。"""
from __future__ import annotations

import yaml

from .claims import derive_app_object_claim
from .constants import (
    APP_CROSS_CUTTING_ROOTS,
    APP_LIB_ROOT,
    APP_ROOT,
    APP_SOURCE_SUFFIX,
    APP_TEST_LAYERS,
    APP_TEST_NON_OBJECT_IDENTITY_METHOD,
    APP_TEST_ROOT,
    CLAIM_METHOD_CONFIDENCE,
    CLOUD_SOURCE_SUFFIXES,
    CLOUD_TEST_SUPPORT_ROOT,
    PAGE_OBJECT_CONTRACT_PATH,
    ROOT,
)
from .identity import (
    derive_app_layer,
    derive_app_cross_cutting_root,
    derive_app_cross_cutting_target_path,
    derive_app_target_path,
    derive_app_test_non_object_identity,
    derive_app_test_target_path,
    derive_app_test_target_shape_identity,
    derive_cloud_source_identity,
    derive_cloud_test_identity,
)
from .roster import ObjectRoster
from .topology import is_cloud_test_file, iter_files, repo_relative, service_domains


def scan_cloud(roster: ObjectRoster) -> tuple[list[dict], list[dict], list[str]]:
    """扫描云侧 production 与测试文件，返回 ``(rows, findings, supportPaths)``。"""
    rows: list[dict] = []
    findings: list[dict] = []
    support_rows: list[str] = []
    for service_relative, (owner, domain) in sorted(service_domains().items()):
        service = ROOT / service_relative
        internal = service / "internal"
        for path in iter_files(internal, CLOUD_SOURCE_SUFFIXES):
            parts = path.relative_to(internal).parts
            identity = derive_cloud_source_identity(parts)
            if identity is None:
                # `internal/<domain>/<context>/...` 是 platform-ops 的历史多余前缀。
                nested = derive_cloud_source_identity(parts[1:]) if parts else None
                if nested is not None and parts and parts[0] == domain:
                    identity = nested
            if identity is None:
                findings.append(
                    {
                        "kind": "cloud_unowned_source",
                        "path": repo_relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": "internal/<context>/<object>/<layer> 不可反推",
                    }
                )
                continue
            context, object_name, layer = identity
            record = roster.by_key.get((domain, context, object_name))
            if record is None:
                findings.append(
                    {
                        "kind": "cloud_source_without_object",
                        "path": repo_relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": f"{domain}.{context}.{object_name} 不在 ContractGraph roster",
                    }
                )
                continue
            rows.append(
                {
                    "side": "cloud",
                    "role": "test" if is_cloud_test_file(path) else "production",
                    "path": repo_relative(path),
                    "objectId": record["objectId"],
                    "domain": domain,
                    "context": context,
                    "objectName": object_name,
                    "currentLayer": layer,
                    "targetLayer": layer,
                    "targetPath": repo_relative(path),
                    "status": "canonical",
                    "method": "cloud_path_exact",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cloud_path_exact"],
                }
            )
        tests = service / "tests"
        for path in iter_files(tests, CLOUD_SOURCE_SUFFIXES):
            parts = path.relative_to(tests).parts
            if parts and parts[0] == CLOUD_TEST_SUPPORT_ROOT:
                support_rows.append(repo_relative(path))
                continue
            identity = derive_cloud_test_identity(parts)
            if identity is None:
                findings.append(
                    {
                        "kind": "cloud_unowned_test",
                        "path": repo_relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": "tests/<layer>/<context>/<object> 不可反推",
                    }
                )
                continue
            test_layer, context, object_name = identity
            record = roster.by_key.get((domain, context, object_name))
            if record is None:
                findings.append(
                    {
                        "kind": "cloud_test_without_object",
                        "path": repo_relative(path),
                        "owner": owner,
                        "domain": domain,
                        "reason": f"{domain}.{context}.{object_name} 不在 ContractGraph roster",
                    }
                )
                continue
            rows.append(
                {
                    "side": "cloud",
                    "role": f"test:{test_layer}",
                    "path": repo_relative(path),
                    "objectId": record["objectId"],
                    "domain": domain,
                    "context": context,
                    "objectName": object_name,
                    "currentLayer": test_layer,
                    "targetLayer": test_layer,
                    "targetPath": repo_relative(path),
                    "status": "canonical",
                    "method": "cloud_path_exact",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cloud_path_exact"],
                }
            )
    return rows, findings, sorted(support_rows)


def load_page_claims() -> tuple[dict[str, list[str]], list[dict]]:
    """载入页面 → object_ids，返回 ``(claims, pages)``；claims 键为仓库相对路径。"""
    document = yaml.safe_load(
        (ROOT / PAGE_OBJECT_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    source_root = str(document.get("source_path_root") or APP_ROOT.as_posix())
    claims: dict[str, list[str]] = {}
    pages: list[dict] = []
    for page in document.get("pages") or []:
        source_path = str(page.get("source_path") or "")
        if not source_path:
            continue
        relative_path = f"{source_root}/{source_path}"
        object_ids = sorted(str(value) for value in (page.get("object_ids") or []))
        pages.append(
            {
                "pageId": str(page.get("page_id") or ""),
                "path": relative_path,
                "pageKind": str(page.get("page_kind") or ""),
                "objectIds": object_ids,
            }
        )
        if object_ids:
            claims[relative_path] = object_ids
    return claims, sorted(pages, key=lambda item: item["path"])


def scan_app(
    roster: ObjectRoster,
    page_claims: dict[str, list[str]],
) -> tuple[list[dict], list[dict]]:
    """扫描端侧 lib/test 文件，派生对象归属与迁移目标。"""
    rows: list[dict] = []
    findings: list[dict] = []

    lib_root = ROOT / APP_LIB_ROOT
    for path in iter_files(lib_root, {APP_SOURCE_SUFFIX}):
        relative_path = repo_relative(path)
        parts = path.relative_to(lib_root).parts
        claim = derive_app_object_claim(parts, roster, page_claims, relative_path)
        layer = derive_app_layer(parts, roster)
        row = {
            "side": "app",
            "role": "production",
            "path": relative_path,
            "method": claim["method"],
            "confidence": CLAIM_METHOD_CONFIDENCE[claim["method"]],
            "aliasTier": claim.get("aliasTier"),
            "currentLayer": layer,
            "objectIds": claim["objectIds"],
            "contextIds": claim.get("contextIds", []),
            "ambiguous": claim["ambiguous"],
        }
        row["domains"] = claim.get("domains", [])
        if claim["objectIds"] and not claim["ambiguous"]:
            record = roster.objects[claim["objectIds"][0]]
            # 已处于目标形态时层由物理位置精确给出；page_object_contract 命中即证明
            # 该文件是入向表现层；其余情况不猜层，层不可派生时如实标记，交由对应
            # domain 流在迁移时决定。
            target_layer = (
                claim.get("targetLayer")
                or layer
                or ("presentation" if claim["method"] == "page_object_contract" else None)
            )
            row.update(
                {
                    "objectId": record["objectId"],
                    "domain": record["domain"],
                    "context": record["context"],
                    "objectName": record["objectName"],
                    "targetLayer": target_layer,
                }
            )
            if target_layer is None:
                row.update({"status": "layer_unresolved", "targetPath": None})
                findings.append(
                    {
                        "kind": "app_layer_unresolved",
                        "path": relative_path,
                        "method": claim["method"],
                        "candidates": [record["objectId"]],
                        "reason": "对象归属明确但现状路径未表达层角色，目标层待裁决",
                    }
                )
            elif claim["method"] == "app_target_shape":
                # 已在目标位置：目标路径就是自身，不做重构造。重构造会拍平层内
                # 合法子路径（`presentation/widgets/card.dart` → `presentation/card.dart`），
                # 破坏 derive(derive(p)) == derive(p)。
                row.update({"status": "canonical", "targetPath": relative_path})
            else:
                row.update(
                    {
                        "status": "mappable",
                        "targetPath": derive_app_target_path(
                            record["domain"],
                            record["context"],
                            record["objectName"],
                            target_layer,
                            path.name,
                        ),
                    }
                )
        elif claim["ambiguous"]:
            multi_page = claim["method"] == "page_object_contract"
            row.update(
                {
                    "status": "multi_object_page" if multi_page else "ambiguous",
                    "targetLayer": "presentation" if multi_page else layer,
                    "targetPath": None,
                }
            )
            findings.append(
                {
                    "kind": "app_multi_object_page"
                    if multi_page
                    else "app_ambiguous_claim",
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim["objectIds"] or claim.get("contextIds", []),
                    "reason": "页面横跨多个对象，presentation 归属需先拆页"
                    if multi_page
                    else "多个候选对象/上下文，需业务裁决，派生器不代选",
                }
            )
        elif claim["method"] in {"context_only", "domain_only"}:
            row.update(
                {
                    "status": claim["method"],
                    "targetLayer": layer,
                    "targetPath": None,
                }
            )
            findings.append(
                {
                    "kind": f"app_{claim['method']}",
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim.get("contextIds") or claim.get("domains", []),
                    "reason": "只能反推到 bounded context / domain，对象归属待裁决",
                }
            )
        else:
            root = derive_app_cross_cutting_root(parts)
            target_path = derive_app_cross_cutting_target_path(root, parts)
            # 已经物理落在横切根下的文件是「搬迁完成」，不是「无法反推的待裁决项」；
            # 继续记为 finding 会随 W1b 推进不断累积假账。
            already_placed = target_path == relative_path
            row.update(
                {
                    "method": "cross_cutting",
                    "confidence": CLAIM_METHOD_CONFIDENCE["cross_cutting"],
                    "crossCuttingRoot": root,
                    "targetLayer": None,
                    "targetPath": target_path,
                    "status": "canonical_cross_cutting"
                    if already_placed
                    else "cross_cutting",
                }
            )
            if not already_placed:
                findings.append(
                    {
                        "kind": "app_unowned_source",
                        "path": relative_path,
                        "method": "unowned",
                        "candidates": [],
                        "reason": f"无法反推对象，暂归横切面 {APP_CROSS_CUTTING_ROOTS[root]}",
                    }
                )
        rows.append(row)

    test_root = ROOT / APP_TEST_ROOT
    for path in iter_files(test_root, {APP_SOURCE_SUFFIX}):
        relative_path = repo_relative(path)
        parts = path.relative_to(test_root).parts
        test_layer = parts[0] if parts and parts[0] in APP_TEST_LAYERS else None
        inner = parts[1:] if test_layer else parts
        # 已处于测试目标形态时身份由物理位置精确决定，别名启发式必须让位，否则
        # `content/content/post/comment/x_test.dart` 会被深层段劫持成 content.comment。
        shaped_test = (
            derive_app_test_target_shape_identity(inner, roster) if test_layer else None
        )
        if shaped_test is not None:
            claim = {
                "method": "app_target_shape",
                "objectIds": [roster.by_key[shaped_test]["objectId"]],
                "ambiguous": False,
                "aliasTier": None,
            }
        else:
            claim = derive_app_object_claim(inner, roster, page_claims, relative_path)
        non_object_identity = (
            derive_app_test_non_object_identity(test_layer, inner)
            if shaped_test is None
            else None
        )
        row = {
            "side": "app",
            "role": f"test:{test_layer}" if test_layer else "test",
            "path": relative_path,
            "method": claim["method"],
            "confidence": CLAIM_METHOD_CONFIDENCE[claim["method"]],
            "aliasTier": claim.get("aliasTier"),
            "currentLayer": test_layer,
            "objectIds": claim["objectIds"],
            "contextIds": claim.get("contextIds", []),
            "ambiguous": claim["ambiguous"],
        }
        if claim["objectIds"] and not claim["ambiguous"] and test_layer:
            record = roster.objects[claim["objectIds"][0]]
            row.update(
                {
                    "objectId": record["objectId"],
                    "domain": record["domain"],
                    "context": record["context"],
                    "objectName": record["objectName"],
                    "targetLayer": test_layer,
                    # 已在 `test/<layer>/service/<service>/<context>/<object>/`
                    # 目标形态时目标
                    # 路径即自身（保留对象下可选子路径），否则按目标形态构造。
                    "targetPath": relative_path
                    if shaped_test is not None
                    else derive_app_test_target_path(
                        test_layer,
                        record["domain"],
                        record["context"],
                        record["objectName"],
                        path.name,
                    ),
                    "status": "canonical" if shaped_test is not None else "mappable",
                }
            )
        elif non_object_identity is not None:
            row.update(
                {
                    "method": APP_TEST_NON_OBJECT_IDENTITY_METHOD,
                    "confidence": CLAIM_METHOD_CONFIDENCE[
                        APP_TEST_NON_OBJECT_IDENTITY_METHOD
                    ],
                    "testIdentityKind": non_object_identity["kind"],
                    "testIdentityRoot": non_object_identity["root"],
                    "status": non_object_identity["status"],
                    # 这些根是测试树的终态位置；不存在待搬迁的 object target。
                    "targetPath": relative_path,
                }
            )
        else:
            if claim["ambiguous"]:
                status = "ambiguous"
                kind = "app_ambiguous_test"
            elif claim["method"] in {"context_only", "domain_only"}:
                status = claim["method"]
                kind = f"app_{claim['method']}_test"
            elif not test_layer:
                status = "unknown_test_root"
                kind = "app_unknown_test_root"
            else:
                status = "unowned"
                kind = "app_unowned_test"
            row.update({"status": status, "targetPath": None})
            findings.append(
                {
                    "kind": kind,
                    "path": relative_path,
                    "method": claim["method"],
                    "candidates": claim["objectIds"]
                    or claim.get("contextIds")
                    or claim.get("domains", []),
                    "reason": "端侧测试无法唯一反推对象",
                }
            )
        rows.append(row)
    return rows, findings


def app_top_level_tree(relative_path: str) -> str:
    parts = relative_path.split("/")
    if len(parts) >= 3 and parts[1] == "lib":
        return f"lib/{parts[2]}" if len(parts) > 3 else "lib/<root>"
    if len(parts) >= 3 and parts[1] == "test":
        return f"test/{parts[2]}" if len(parts) > 3 else "test/<root>"
    return "/".join(parts[:2])
