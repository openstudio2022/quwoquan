"""校验全域 commercial-ready operation 的对象级告警与仪表盘覆盖。

判定口径（domain-agnostic，没有域分支、没有对象清单文件）：

* 业务真相源只有 `quwoquan_service/generated/contract_graph.json`；
  domain -> service 标签只从 `services/<service>/contracts/domain.yaml` 推导，运行分母再与
  canonical `docker-compose.gamma-local.yaml` 活跃 workload 求交。
* 每个 operation 必须声明 `telemetry.metric` 与数值化 `slo`。
* 每个 operation 必须有 `quwoquan_<domain>_contract_operation_requests_total` /
  `..._duration_seconds_bucket` 两条 recording rule，label 与 expr 由 ContractGraph
  的 method / pathTemplate / metric / commercial.status / slo 派生。
* 每个 `commercial.status == ready` 的 operation 的两个 record metric 都必须被
  真实 alerting rule 与 dashboard target 的 PromQL selector 消费（`operation` +
  `contract_metric` 正向匹配）。注释、annotation、panel description、legend 不计证据。
* 任何消费 `quwoquan_<domain>_contract_operation_*` 的 selector 都必须能匹配
  ContractGraph 中该域至少一个 operation，防止对象改名后留下死告警。
* `commercial.status != ready` 的 operation 按域输出「待商用」分类统计，不阻断。

对象分母是 ContractGraph 中活跃 workload 的全部 object，按契约面自动分类（不是
allowlist，新对象自动纳入）：

* `ready`：拥有 >=1 个 ready operation，必须满足上述全部 operation 级覆盖。
* `pending_commercial`：拥有 operation 但全部待商用，recording rule 仍然生成，翻 ready 即自动纳入告警。
* `runtime_surface_only`：不拥有任何 operation，但拥有 runtimeEntrypoint（projector /
  internal_port / subscription / middleware / external_port）。这类对象没有 HTTP
  operation，ContractGraph 也没有为 runtimeEntrypoint 声明 telemetry/slo，因此不存在
  可派生的 operation 级 SLO 告警口径；一旦 runtimeEntrypoint 声明 telemetry.metric，
  本门禁立即要求同等覆盖。
* 既无 operation 又无 runtimeEntrypoint 的对象没有任何契约面，直接 BLOCK。

`/internal/` 路径与 `principal: service` 的服务间 operation 不豁免，与面向 App 的
operation 使用同一套判定。

`telemetry.metric` 的语义在本仓已由既有事实裁定为**契约层逻辑标识（join key）**，不是
series 发射承诺：

* 唯一具备 SLO 形状的运行时指标是共享中间件注册的 `http_server_requests_total`
  `{service,route,method,status}` 与 `http_server_duration_seconds{service,route,method}`，
  既没有 per-operation series 名，也没有 `contract_metric` label。
* 声明名不遵守 Prometheus 指标类型后缀约定（`_total`/`_seconds`/...），而真实注册的
  series 绝大多数遵守；声明名在 PromQL 里只以 `contract_metric` label 值出现。

因此本门禁断言：声明名只能以 label 形式被消费。任何 PromQL（alerting expr / dashboard
target）把声明名放在 **series 位置**即 BLOCK，除非确实有服务注册了同名 series——同名
series 集合由 `load_emitted_series()` 每次运行从 Go `prometheus.*Opts` 与 Python
`Counter/Gauge/Histogram/Summary` 现场扫描得出，不是 allowlist。`summary` / `description`
等人类注解文本不是 PromQL，既不计覆盖证据也不触发 BLOCK。

recording rules、覆盖告警与覆盖仪表盘都由本脚本从 ContractGraph 生成（`--write`），
默认模式同时校验语义覆盖与生成产物漂移。
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from .constants import ALERTS_ROOT, CONTRACT_GRAPH, DASHBOARDS_ROOT, SERVICES_ROOT
from .contract_inputs import (
    load_domain_services,
    load_operations,
    runtime_domain_services,
)
from .generated_docs import write_generated_documents
from .models import (
    ContractInputError,
    OBJECT_SURFACE_NONE,
    OBJECT_SURFACE_PENDING,
    OBJECT_SURFACE_READY,
    OBJECT_SURFACE_RUNTIME_ONLY,
    VerificationReport,
)
from .verification import verify_coverage


def _print_report(report: VerificationReport) -> None:
    surfaces = collections.Counter(surface.classification for surface in report.object_surfaces)
    print(
        f"[object-alert-coverage] objects={len(report.object_surfaces)} "
        f"operations={report.operations} ready={report.ready_operations} "
        f"domains={len(report.domains)}"
    )
    orphans = report.declared_metrics - len(report.emitted_metrics)
    print(
        f"  telemetry.metric 语义=契约层逻辑标识（只作 contract_metric label 消费）: "
        f"declared={report.declared_metrics} 同名 series 实际存在="
        f"{len(report.emitted_metrics)} 仅逻辑标识={orphans}"
    )
    if report.emitted_metrics:
        print("    同名 series: " + ", ".join(report.emitted_metrics))
    print(
        "  对象契约面: "
        + ", ".join(
            f"{name}={surfaces[name]}"
            for name in (
                OBJECT_SURFACE_READY,
                OBJECT_SURFACE_PENDING,
                OBJECT_SURFACE_RUNTIME_ONLY,
                OBJECT_SURFACE_NONE,
            )
        )
    )
    for domain in report.domains:
        pending = sum(count for _, count in domain.blocked_by_gap)
        objects = ", ".join(f"{name}:{count}" for name, count in domain.objects)
        detail = (
            " 待商用=" + ", ".join(f"{gap}:{count}" for gap, count in domain.blocked_by_gap)
            if domain.blocked_by_gap
            else ""
        )
        print(
            f"  - {domain.domain} ({domain.service}): objects[{objects}] "
            f"operations={domain.operations} ready={domain.ready} pending={pending}{detail}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-graph", type=Path, default=CONTRACT_GRAPH)
    parser.add_argument("--alerts-root", type=Path, default=ALERTS_ROOT)
    parser.add_argument("--dashboards-root", type=Path, default=DASHBOARDS_ROOT)
    parser.add_argument("--services-root", type=Path, default=SERVICES_ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="从 ContractGraph 重建对象级 recording rules、覆盖告警与覆盖仪表盘",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.write:
        try:
            domain_services = load_domain_services(args.services_root)
            operations = load_operations(args.contract_graph, domain_services)
            runtime_services = runtime_domain_services(
                domain_services, args.services_root
            )
            operations = [
                operation
                for operation in operations
                if operation.service in runtime_services.values()
            ]
            count = write_generated_documents(
                operations, args.alerts_root, args.dashboards_root
            )
        except ContractInputError as error:
            print(f"[object-alert-coverage] BLOCK: {error}", file=sys.stderr)
            return 1
        print(f"[object-alert-coverage] 生成 {count} 份 ContractGraph 派生产物")
        return 0

    report = verify_coverage(
        contract_graph=args.contract_graph,
        alerts_root=args.alerts_root,
        dashboards_root=args.dashboards_root,
        services_root=args.services_root,
    )
    _print_report(report)
    if report.issues:
        print(
            "[object-alert-coverage] FAIL: ready operation 对象级告警覆盖不完整 "
            f"({len(report.issues)} 项)",
            file=sys.stderr,
        )
        for issue in report.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[object-alert-coverage] OK")
    return 0
