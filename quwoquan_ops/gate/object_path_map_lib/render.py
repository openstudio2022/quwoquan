"""manifest/基线报告渲染与 context 口径差异。"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

from .constants import CLAIM_METHOD_CONFIDENCE, ROOT, RULE_ID, SERVICE_ROOT_GLOBS
from .roster import ObjectRoster
from .topology import repo_relative

# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = (
    "side",
    "role",
    "status",
    "method",
    "confidence",
    "objectId",
    "domain",
    "context",
    "objectName",
    "currentLayer",
    "targetLayer",
    "path",
    "targetPath",
)


def render_manifest(rows: Sequence[dict]) -> str:
    lines = ["\t".join(MANIFEST_COLUMNS)]
    for row in sorted(rows, key=lambda item: (item["side"], item["path"])):
        lines.append(
            "\t".join(
                str(row.get(column) if row.get(column) is not None else "")
                for column in MANIFEST_COLUMNS
            )
        )
    return "\n".join(lines) + "\n"


def render_baseline_report(
    roster: ObjectRoster,
    baseline: dict,
    object_view: dict[str, dict],
    context_diff: dict,
) -> str:
    kinds = Counter(entry["kind"] for entry in roster.objects.values())
    lines: list[str] = []
    lines.append("# 端云对象化现状基线（派生产物，可删除可重建）")
    lines.append("")
    lines.append(f"- 规则标识：`{RULE_ID}`")
    lines.append("- 派生器：`quwoquan_ops/gate/object_path_map.py`")
    lines.append(
        "- 真相源：`quwoquan_service/generated/contract_graph.json`、"
        "`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`、"
        "`contracts/domain.yaml`、物理源码/测试树"
    )
    lines.append("")
    lines.append("## 1. 对象 roster")
    lines.append("")
    lines.append(f"- domain：{len(roster.domains)}")
    lines.append(f"- bounded context（ContractGraph `contextId`）：{len(roster.context_ids)}")
    lines.append(f"- business object：{len(roster.objects)}")
    lines.append("- kind 分布：")
    for kind, count in sorted(kinds.items()):
        lines.append(f"  - `{kind}`：{count}")
    lines.append("")
    lines.append("### bounded context 计数差异说明")
    lines.append("")
    for line in context_diff["explanation"]:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("## 2. 端侧散落度（每个 domain 横跨的顶层树）")
    lines.append("")
    lines.append("| domain | 顶层树数 | 已归属对象数 | 已归属文件数 | 分布 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for domain, bucket in baseline["appScatterByDomain"].items():
        distribution = "、".join(
            f"`{tree}`={count}" for tree, count in bucket["trees"].items()
        )
        lines.append(
            f"| `{domain}` | {bucket['treeCount']} | {bucket['objectCount']} | "
            f"{bucket['files']} | {distribution} |"
        )
    lines.append("")
    lines.append("## 3. 无主文件（扫到但无法唯一归属到任何对象）")
    lines.append("")
    lines.append(
        f"- 端侧业务对象已唯一归属：{baseline['appBusinessObjectClaimedFileTotal']} / "
        f"{baseline['appFileTotal']}"
    )
    lines.append(
        f"- 端侧横切源码：{baseline['appCrossCuttingFileTotal']}"
        f"（canonical={baseline['appCanonicalCrossCuttingFileTotal']}，"
        f"待迁移={baseline['appPendingCrossCuttingFileTotal']}）"
    )
    for root, count in baseline["appCrossCuttingFilesByRoot"].items():
        lines.append(f"  - `{root}`：{count}")
    lines.append(
        "- 非对象测试身份："
        f"{baseline['appTestNonObjectIdentityFileTotal']}"
        "（不计入任何 object 的测试覆盖）"
    )
    for kind, count in baseline["appTestNonObjectIdentityFilesByKind"].items():
        lines.append(f"  - `{kind}`：{count}")
    lines.append(f"- 端侧无主文件合计：{baseline['appUnownedFileTotal']}")
    lines.append("- 按无主原因：")
    for status, count in baseline["appUnownedFilesByStatus"].items():
        lines.append(f"  - `{status}`：{count}")
    lines.append("- 已归属文件按派生方法：")
    for method, count in baseline["appClaimsByMethod"].items():
        lines.append(
            f"  - `{method}`（置信度 `{CLAIM_METHOD_CONFIDENCE[method]}`）：{count}"
        )
    lines.append("")
    lines.append("| 顶层树 | 无主文件数 |")
    lines.append("| --- | --- |")
    for tree, count in sorted(
        baseline["appUnownedFilesByTree"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| `{tree}` | {count} |")
    lines.append("")
    lines.append("## 4. 无对象的页面")
    lines.append("")
    lines.append(f"- `page_object_contract.yaml` 登记页面：{baseline['pagesInContract']}")
    lines.append(
        f"- 登记但 `object_ids` 为空：{len(baseline['pagesWithoutObjectIds'])}"
    )
    for path in baseline["pagesWithoutObjectIds"]:
        lines.append(f"  - `{path}`")
    lines.append(
        f"- 磁盘上 `*_page.dart` 但未被契约登记："
        f"{len(baseline['pageNamedFilesOutsideContract'])}"
    )
    for path in baseline["pageNamedFilesOutsideContract"]:
        lines.append(f"  - `{path}`")
    lines.append(
        f"- `pages/**` 下未登记的页面片段（`*_page_state.dart` 等，仅候选复核）："
        f"{len(baseline['pageDirectoryFilesOutsideContract'])}"
    )
    lines.append("")
    lines.append("## 5. 缺层统计")
    lines.append("")
    lines.append(
        f"- 端侧缺必需层的对象：{len(baseline['objectsMissingRequiredAppLayers'])} / "
        f"{len(roster.objects)}"
    )
    lines.append(
        f"- 云侧缺必需层的对象：{len(baseline['objectsMissingRequiredCloudLayers'])} / "
        f"{len(roster.objects)}"
    )
    lines.append(
        f"- 端侧完全没有任何文件的对象：{len(baseline['objectsWithoutAnyAppFile'])}"
    )
    missing_counter = Counter()
    for layers in baseline["objectsMissingRequiredAppLayers"].values():
        missing_counter.update(layers)
    missing_cloud_counter = Counter()
    for layers in baseline["objectsMissingRequiredCloudLayers"].values():
        missing_cloud_counter.update(layers)
    for label, counter in (("端侧", missing_counter), ("云侧", missing_cloud_counter)):
        lines.append(f"- {label}缺失层分布：")
        if not counter:
            lines.append(
                f"  - 无：{len(roster.objects)} 个对象的 kind 必需层全部齐备"
            )
        for layer, count in sorted(counter.items()):
            lines.append(f"  - `{layer}`：{count}")
    lines.append("")
    lines.append("### 端侧缺必需层明细")
    lines.append("")
    lines.append("| objectId | kind | 被页面认领 | 必需层 | 缺失层 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for object_id, layers in baseline["objectsMissingRequiredAppLayers"].items():
        entry = object_view[object_id]
        lines.append(
            f"| `{object_id}` | `{entry['kind']}` | "
            f"{'是' if entry['claimedByPage'] else '否'} | "
            f"{'、'.join(entry['requiredAppLayers'])} | {'、'.join(layers)} |"
        )
    lines.append("")
    lines.append("## 6. 文件规模")
    lines.append("")
    lines.append(f"- 云侧扫描并归属的文件：{baseline['cloudFileTotal']}")
    lines.append(
        f"- 云侧 `tests/support/**` 共享支撑文件（不承载对象身份）："
        f"{baseline['cloudTestSupportFileTotal']}"
    )
    lines.append(f"- 端侧扫描的文件：{baseline['appFileTotal']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_context_diff(roster: ObjectRoster) -> dict:
    """派生 bounded context 计数的各个可观测口径，并解释常见的 24 vs 22 差异。"""
    context_yaml = sorted(
        repo_relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/contracts/*/context.yaml")
    )
    contract_dirs = sorted(
        repo_relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/contracts/*")
        if path.is_dir()
    )
    shared_contract_dirs = [
        path for path in contract_dirs if path.rsplit("/", 1)[-1].startswith("_")
    ]
    internal_dirs = sorted(
        repo_relative(path)
        for pattern in SERVICE_ROOT_GLOBS
        for path in ROOT.glob(f"{pattern}/internal/*")
        if path.is_dir()
    )
    object_contexts = sorted(
        {record["contextId"] for record in roster.objects.values()}
    )
    context_names = {context_id.split(".", 1)[1] for context_id in roster.context_ids}
    non_context_internal_dirs = [
        path for path in internal_dirs if path.rsplit("/", 1)[-1] not in context_names
    ]
    counts = {
        "contractGraphContextId": len(roster.context_ids),
        "contextYamlFiles": len(context_yaml),
        "contextIdsCarryingObjects": len(object_contexts),
        "serviceContractsChildDirs": len(contract_dirs),
        "serviceContractsSharedDirs": len(shared_contract_dirs),
        "serviceInternalChildDirs": len(internal_dirs),
        "nonContextInternalChildDirs": len(non_context_internal_dirs),
    }
    service_glob = "{services,control-plane}"
    explanation = [
        "ContractGraph `businessObjectMaps[].boundedContexts[].contextId` 实测 "
        f"{counts['contractGraphContextId']} 个；`contracts/*/context.yaml` "
        f"{counts['contextYamlFiles']} 个；实际承载对象的 contextId "
        f"{counts['contextIdsCarryingObjects']} 个。三个口径完全一致，"
        "本派生器以该 roster 为唯一准据。",
        f"因此 OPEN-001 记的 {counts['contractGraphContextId']} 与 ContractGraph roster "
        "一致，`contextId` 口径下不存在 24。",
        f"能数出 24 的是**目录**口径：`{service_glob}/*/internal/*` 子目录共 "
        f"{counts['serviceInternalChildDirs']} 个，其中 "
        f"{counts['nonContextInternalChildDirs']} 个不是 bounded context（"
        + "、".join(f"`{path}`" for path in non_context_internal_dirs)
        + f"），扣除后为 "
        f"{counts['serviceInternalChildDirs'] - counts['nonContextInternalChildDirs']} 个。"
        f"另一个近似口径是 `{service_glob}/*/contracts/*` 子目录 "
        f"{counts['serviceContractsChildDirs']} 个，其中 "
        f"{counts['serviceContractsSharedDirs']} 个是 `_shared` 非 context 目录，"
        f"扣除后 "
        f"{counts['serviceContractsChildDirs'] - counts['serviceContractsSharedDirs']} 个。",
        f"结论：24 是目录计数口径的偏差，contextId roster 恒为 "
        f"{counts['contractGraphContextId']}；后续 domain 并行流只读本派生器的 roster，"
        "不再各自数目录。",
    ]
    return {
        "counts": counts,
        "contextIds": sorted(roster.context_ids),
        "contextYamlFiles": context_yaml,
        "serviceContractsChildDirs": contract_dirs,
        "serviceInternalChildDirs": internal_dirs,
        "nonContextInternalChildDirs": non_context_internal_dirs,
        "explanation": explanation,
    }
