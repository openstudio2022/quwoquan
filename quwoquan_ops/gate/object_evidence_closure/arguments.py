"""对象 × 层 × 三层测试入口的 readiness 结构性证据闭合门禁。

判定完全来自 metadata 装载与图构建管线派生出的 ContractGraph：
`readinessEvidence` 由 `quwoquan_service/internal/metadata/load` 从受版本控制的物理
路径反推，`objectReadiness.missing` 由 `internal/metadata/graph` 的
`implementationEvidenceReady` / `commercialEvidenceReady` 判定。本门禁只把这些 missing
键展开成「对象 × 层」缺口清单，不重算 readiness 规则，避免出现第二套真相。

本门禁只校验**结构性证据**：实现 seam 与三层测试文件真实存在、且证据以 SHA256 绑定到
确切字节。「无缺口」只意味着实现与验证入口已就位，**不意味着任何测试通过**——用例是否
通过属于结果证据，只能由 runner 附加，静态派生永远不得代替。

两条自有断言（都把负担落回契约本身，而不是放宽 readiness 规则）：

1. 页面消费闭合：有 clientContract 但没有被任何页面 `object_ids` 认领的对象，必须能在
   别的对象的页面里被证明消费（页面 `query_slices` 指向该对象），否则报缺口。
2. 领域事件声明闭合：`implementation.outbox` 的必需性由对象自己声明的领域事件**投递
   保证**派生（见 `ast.ClassifyEventDelivery`）。因此有命令的聚合必须**显式表态**：要么
   声明事件，要么写下 `events: []`；连 `events.yaml` 都没有的聚合等于既没声明也没否认，
   会静默拿到发件箱豁免，在这里报缺口。

曾经这里还有第三条「事件投递语义闭合」，把 `channel` 的未知取值与缺键当独立缺口暴露。
它是**没有值域**时的补偿：那时 topic 名、笔误和机制名混在同一个字段里，只能靠 fail-safe
留痕让失控可见。`channel` 拆成受控 `delivery_semantics` 与自由 `topic` 之后，取值域由
`_schemas/events.schema.json` 的 enum 与 required 直接强制，两类情况都在 schema 层就无法
通过，维度随之关闭——这正是当时写在缺口文案里的「取值收敛后本缺口自动关闭」。

结构缺口已进入严格零值模式：任何 STRUCTURAL 维度只要实测大于 0 就直接
BLOCK。历史棘轮基线已退役，既不提供刷新入口，也不允许通过重建基线为缺口发放额度。
`commercial.result_bundle` 和四环境回执仍是 RESULT 证据：它们必须在可信 runner 中完成，
静态结构门只报告、不伪造动态 PASS。

fail-closed：没有 allowlist、没有豁免、没有 warn-only。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .constants import RUN_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help=(
            "显式判定的 ContractGraph JSON（主要供契约测试/已绑定 artifact 使用）；"
            "缺省从当前工作树现场派生，不复用可能陈旧的 committed graph"
        ),
    )
    parser.add_argument(
        "--derive",
        action="store_true",
        help=(
            "改用 build_service_contract_view.py + qwq_contract generate 以真实仓库根"
            "现场派生一份图（需要 Go 工具链，约 30 秒）"
        ),
    )
    parser.add_argument(
        "--require-commercial-readiness",
        action="store_true",
        help=(
            "结构证据严格为零后，以六项完整 trust input 直接调用 canonical Go "
            "evaluator；缺项或协议错误返回 2"
        ),
    )
    parser.add_argument(
        "--readiness-bundle",
        type=Path,
        default=None,
        help="untrusted ReadinessResultBundle JSON; trust comes from signed receipts",
    )
    parser.add_argument(
        "--signed-current-snapshot",
        type=Path,
        default=None,
        help="package-bound Ed25519 SignedCurrentSnapshot JSON",
    )
    parser.add_argument(
        "--snapshot-keyring",
        type=Path,
        default=None,
        help="trusted snapshot authority public-key keyring JSON",
    )
    parser.add_argument(
        "--runner-keyring",
        type=Path,
        default=None,
        help="trusted runner public-key keyring JSON",
    )
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=None,
        help="restricted root containing detached-signed readiness receipts",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=None,
        help="restricted content-addressed readiness evidence root",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=RUN_DIR,
        help="缺口清单输出目录（默认落在 .qwq_output 下，可删除可重建）",
    )
    arguments = parser.parse_args()
    if arguments.derive and arguments.graph is not None:
        parser.error("--derive 与 --graph 互斥：判定源必须唯一")
    commercial_values = commercial_input_values(arguments)
    if any(value is not None for value in commercial_values.values()) and not (
        arguments.require_commercial_readiness
    ):
        parser.error(
            "dynamic readiness inputs require --require-commercial-readiness"
        )
    return arguments


def commercial_input_values(arguments: argparse.Namespace) -> dict[str, Path | None]:
    return {
        "resultBundle": getattr(arguments, "readiness_bundle", None),
        "signedCurrentSnapshot": getattr(
            arguments, "signed_current_snapshot", None
        ),
        "snapshotKeyring": getattr(arguments, "snapshot_keyring", None),
        "runnerKeyring": getattr(arguments, "runner_keyring", None),
        "receiptRoot": getattr(arguments, "receipt_root", None),
        "evidenceRoot": getattr(arguments, "evidence_root", None),
    }
