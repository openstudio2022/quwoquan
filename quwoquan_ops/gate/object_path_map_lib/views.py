"""对象聚合视图与现状基线。"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Sequence

from .constants import (
    APP_LIB_ROOT,
    APP_SOURCE_SUFFIX,
    APP_TEST_NON_OBJECT_IDENTITY_METHOD,
    CLOUD_EXTERNAL_REFERENCE_EITHER,
    FORBIDDEN_APP_LAYERS_BY_KIND,
    ROOT,
    required_app_layers,
    required_cloud_layers,
)
from .identity import derive_page_physical_owner
from .roster import ObjectRoster
from .scan import app_top_level_tree
from .topology import iter_files, repo_relative


def build_object_view(
    roster: ObjectRoster,
    cloud_rows: Sequence[dict],
    app_rows: Sequence[dict],
    page_claims: dict[str, list[str]],
    pages: Sequence[dict] | None = None,
) -> dict[str, dict]:
    """按对象聚合端云物理文件与层出现情况。"""
    page_records = list(pages) if pages is not None else [
        {"path": path, "objectIds": object_ids}
        for path, object_ids in sorted(page_claims.items())
    ]
    page_participant_paths: dict[str, set[str]] = defaultdict(set)
    page_owner_paths: dict[str, set[str]] = defaultdict(set)
    for page in page_records:
        page_path = str(page.get("path") or "")
        if not page_path:
            continue
        for object_id in page.get("objectIds") or []:
            if object_id in roster.objects:
                page_participant_paths[object_id].add(page_path)
        physical_owner = derive_page_physical_owner(page_path, roster)
        if physical_owner is not None:
            page_owner_paths[physical_owner].add(page_path)

    view: dict[str, dict] = {}
    for object_id, record in roster.objects.items():
        client_operations = roster.app_client_contract_operations.get(object_id, ())
        participant_paths = sorted(page_participant_paths.get(object_id, ()))
        owner_paths = sorted(page_owner_paths.get(object_id, ()))
        view[object_id] = {
            **record,
            "claimedByPage": bool(participant_paths),
            "pageParticipantPaths": participant_paths,
            "ownsPage": bool(owner_paths),
            "pageOwnerPaths": owner_paths,
            "hasAppClientContractOperation": bool(client_operations),
            "appClientContractOperationIds": list(client_operations),
            "cloud": {"layers": {}, "tests": {}},
            "app": {"layers": {}, "tests": {}},
        }
    for row in cloud_rows:
        entry = view[row["objectId"]]["cloud"]
        bucket = "tests" if row["role"].startswith("test") else "layers"
        entry[bucket].setdefault(row["currentLayer"], []).append(row["path"])
    for row in app_rows:
        object_id = row.get("objectId")
        if not object_id:
            continue
        entry = view[object_id]["app"]
        if row["role"].startswith("test"):
            entry["tests"].setdefault(row["currentLayer"] or "unknown", []).append(
                row["path"]
            )
        else:
            entry["layers"].setdefault(row.get("targetLayer") or "unknown", []).append(
                row["path"]
            )

    for entry in view.values():
        kind = entry["kind"]
        for side in ("cloud", "app"):
            for bucket in ("layers", "tests"):
                entry[side][bucket] = {
                    layer: sorted(paths)
                    for layer, paths in sorted(entry[side][bucket].items())
                }
        cloud_layers = set(entry["cloud"]["layers"])
        missing_cloud = sorted(set(required_cloud_layers(kind)) - cloud_layers)
        if kind == "external_reference":
            if "application" not in cloud_layers:
                missing_cloud.append("application")
            if not cloud_layers & set(CLOUD_EXTERNAL_REFERENCE_EITHER):
                missing_cloud.append("adapters-or-infrastructure")
        entry["missingCloudLayers"] = sorted(set(missing_cloud))

        app_layers = set(entry["app"]["layers"])
        # 当前两个 machine-readable capability source 只有 clientContract 与页面
        # source owner；物理 domain 文件只能证明结构存在，不能反向证明规格已声明
        # client invariant。没有 canonical object-level invariant fact 时不制造义务。
        expected_app = set(
            required_app_layers(
                has_client_contract_operation=entry[
                    "hasAppClientContractOperation"
                ],
                owns_page=entry["ownsPage"],
                has_client_invariant=False,
            )
        )
        entry["requiredAppLayers"] = sorted(expected_app)
        entry["missingAppLayers"] = sorted(expected_app - app_layers)
        entry["forbiddenAppLayersPresent"] = sorted(
            set(FORBIDDEN_APP_LAYERS_BY_KIND.get(kind, ())) & app_layers
        )
    return view


def build_baseline(
    roster: ObjectRoster,
    cloud_rows: Sequence[dict],
    app_rows: Sequence[dict],
    pages: Sequence[dict],
    object_view: dict[str, dict],
) -> dict:
    """派生现状基线：散落度、无主文件、无对象页面、缺层。"""
    scatter: dict[str, dict] = {}
    for row in app_rows:
        object_id = row.get("objectId")
        if not object_id:
            continue
        domain = roster.objects[object_id]["domain"]
        tree = app_top_level_tree(row["path"])
        bucket = scatter.setdefault(
            domain,
            {"domain": domain, "trees": {}, "files": 0, "objects": set()},
        )
        bucket["trees"][tree] = bucket["trees"].get(tree, 0) + 1
        bucket["files"] += 1
        bucket["objects"].add(object_id)
    for domain, bucket in scatter.items():
        bucket["treeCount"] = len(bucket["trees"])
        bucket["objectCount"] = len(bucket["objects"])
        bucket["objects"] = sorted(bucket["objects"])
        bucket["trees"] = dict(sorted(bucket["trees"].items()))

    # 端侧文件严格分为三类：业务对象、横切面、真正未决。canonical runtime / design
    # system 已有明确 owner，不能继续混入「无主」并强迫归到某个业务对象。
    business_object_rows = [row for row in app_rows if row.get("objectId")]
    cross_cutting_rows = [
        row
        for row in app_rows
        if not str(row.get("role", "production")).startswith("test")
        and not row.get("objectId")
        and row.get("method") == "cross_cutting"
    ]
    non_object_test_rows = [
        row
        for row in app_rows
        if str(row.get("role", "")).startswith("test")
        and not row.get("objectId")
        and row.get("method") == APP_TEST_NON_OBJECT_IDENTITY_METHOD
    ]
    ownerless_rows = [
        row
        for row in app_rows
        if not row.get("objectId")
        and row.get("method")
        not in {"cross_cutting", APP_TEST_NON_OBJECT_IDENTITY_METHOD}
    ]
    unowned_by_tree = Counter(
        app_top_level_tree(row["path"]) for row in ownerless_rows
    )
    unowned_by_status = Counter(row["status"] for row in ownerless_rows)
    cross_cutting_by_root = Counter(
        str(row.get("crossCuttingRoot") or "unknown") for row in cross_cutting_rows
    )
    cross_cutting_by_status = Counter(row["status"] for row in cross_cutting_rows)
    non_object_tests_by_kind = Counter(
        str(row.get("testIdentityKind") or "unknown") for row in non_object_test_rows
    )
    non_object_tests_by_root = Counter(
        str(row.get("testIdentityRoot") or "unknown") for row in non_object_test_rows
    )
    claim_by_method = Counter(
        row["method"] for row in app_rows if row.get("objectId")
    )
    status_totals = Counter(row["status"] for row in app_rows)

    page_paths = {page["path"] for page in pages}
    pages_without_object = [
        page["path"] for page in pages if not page["objectIds"]
    ]
    # 页面形态分两级：`*_page.dart` 是强信号（应是真实页面对象），
    # `pages/**` 下的其他文件多为页面片段（`*_page_state.dart`、`*_widgets.dart`），
    # 只作候选复核，不等同于缺页面契约。
    page_named_files: list[str] = []
    page_directory_files: list[str] = []
    for path in iter_files(ROOT / APP_LIB_ROOT, {APP_SOURCE_SUFFIX}):
        relative_path = repo_relative(path)
        if relative_path in page_paths:
            continue
        if path.name.endswith("_page.dart"):
            page_named_files.append(relative_path)
        elif "pages" in path.relative_to(ROOT / APP_LIB_ROOT).parts:
            page_directory_files.append(relative_path)
    page_named_files.sort()
    page_directory_files.sort()

    missing_app = {
        object_id: entry["missingAppLayers"]
        for object_id, entry in sorted(object_view.items())
        if entry["missingAppLayers"]
    }
    missing_cloud = {
        object_id: entry["missingCloudLayers"]
        for object_id, entry in sorted(object_view.items())
        if entry["missingCloudLayers"]
    }
    objects_without_app_file = sorted(
        object_id
        for object_id, entry in object_view.items()
        if not entry["app"]["layers"] and not entry["app"]["tests"]
    )

    return {
        "appScatterByDomain": dict(sorted(scatter.items())),
        "appUnownedFilesByTree": dict(sorted(unowned_by_tree.items())),
        "appUnownedFilesByStatus": dict(sorted(unowned_by_status.items())),
        "appUnownedFileTotal": len(ownerless_rows),
        "appClaimedFileTotal": len(business_object_rows),
        "appBusinessObjectClaimedFileTotal": len(business_object_rows),
        "appCrossCuttingFilesByRoot": dict(sorted(cross_cutting_by_root.items())),
        "appCrossCuttingFilesByStatus": dict(sorted(cross_cutting_by_status.items())),
        "appCrossCuttingFileTotal": len(cross_cutting_rows),
        "appCanonicalCrossCuttingFileTotal": cross_cutting_by_status[
            "canonical_cross_cutting"
        ],
        "appPendingCrossCuttingFileTotal": len(cross_cutting_rows)
        - cross_cutting_by_status["canonical_cross_cutting"],
        "appTestNonObjectIdentityFilesByKind": dict(
            sorted(non_object_tests_by_kind.items())
        ),
        "appTestNonObjectIdentityFilesByRoot": dict(
            sorted(non_object_tests_by_root.items())
        ),
        "appTestNonObjectIdentityFileTotal": len(non_object_test_rows),
        "appClaimsByMethod": dict(sorted(claim_by_method.items())),
        "appStatusTotals": dict(sorted(status_totals.items())),
        # 搬迁进度：已处于目标形态（对象树或横切根）的端侧文件数。四条 domain 流与
        # W1b 用它衡量收敛，派生对这些文件必须幂等。
        "appCanonicalFileTotal": status_totals["canonical"]
        + status_totals["canonical_cross_cutting"],
        "pagesInContract": len(pages),
        "pagesWithoutObjectIds": pages_without_object,
        "pageNamedFilesOutsideContract": page_named_files,
        "pageDirectoryFilesOutsideContract": page_directory_files,
        "objectsMissingRequiredAppLayers": missing_app,
        "objectsMissingRequiredCloudLayers": missing_cloud,
        "objectsWithoutAnyAppFile": objects_without_app_file,
        "cloudFileTotal": len(cloud_rows),
        "appFileTotal": len(app_rows),
    }
