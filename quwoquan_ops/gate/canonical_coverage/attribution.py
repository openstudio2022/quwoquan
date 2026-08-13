"""端云 production source 归属与逐单元计量。

端侧归属全部经 `object_path_map`，不写第二套规则；云侧对象身份只从物理路径
反推并与 ContractGraph roster 交叉验证。``measure`` 读取落盘产物折算成
``{unit: {metric: entry}}``。除 import 重组外与拆分前逐字一致；被测试
monkeypatch 的符号（``AppAttribution``、``parse_lcov``、``_read_artifact`` 等）
经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import quwoquan_ops.gate.canonical_coverage as cc
from quwoquan_ops.gate import object_path_map as opm

from .constants import (
    APP_COLLECTION_TARGET,
    APP_TEST_TARGET,
    APP_UNIT_PREFIX,
    CLOUD_UNIT_PREFIX,
    KIND_FLUTTER_LCOV,
    METRICS_BY_KIND,
    METRIC_STATUS_UNMEASURED,
    SERVICE_ROOT,
    CoverageError,
    _display,
)
from .parsing import parse_go_coverprofile_files, parse_python_trace_files
from .provenance import artifact_path
from .receipts import validate_artifact_receipt
from .units import (
    _collection_target_language,
    _roster,
    app_cross_cutting_unit,
    app_object_unit,
    cloud_collection_targets,
    cloud_collection_targets_for_unit,
    cloud_cross_cutting_unit,
    cloud_object_unit,
    expected_app_capability_units,
)


class CloudAttribution:
    """Cloud production source → 对象/横切单元的唯一物理归属。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        self.unit_of: dict[str, str] = {}
        self.files_by_unit: dict[str, set[str]] = {}
        service_domains = opm.service_domains()
        for target, domain in sorted(cloud_collection_targets().items()):
            owner, declared_domain = service_domains[target]
            if declared_domain != domain or domain not in roster.domains:
                raise CoverageError(
                    f"{target}: service domain 与 ContractGraph roster 漂移"
                )
            service_root = cc.ROOT / target
            language = _collection_target_language(target)
            suffix = "*.go" if language == "go" else "*.py"
            for path in sorted((service_root / "internal").rglob(suffix)):
                if (
                    language == "go" and path.name.endswith("_test.go")
                ) or path.is_symlink():
                    continue
                identity = opm.derive_cloud_source_identity(
                    path.relative_to(service_root / "internal").parts
                )
                if identity is None:
                    raise CoverageError(
                        f"{_display(path)}: Cloud production source 不是 "
                        "internal/<context>/<object>/<layer>"
                    )
                context, object_name, _layer = identity
                record = roster.by_key.get((domain, context, object_name))
                if record is None:
                    raise CoverageError(
                        f"{_display(path)}: 物理对象 {domain}.{context}.{object_name} "
                        "不在 ContractGraph roster"
                    )
                self._add(
                    path,
                    cloud_object_unit(owner, context, object_name),
                )
            for path in sorted((service_root / "cmd").rglob(suffix)):
                if (
                    not (language == "go" and path.name.endswith("_test.go"))
                    and not path.is_symlink()
                ):
                    self._add(path, cloud_cross_cutting_unit("cmd"))

        for path in sorted((SERVICE_ROOT / "cmd").rglob("*.go")):
            if not path.name.endswith("_test.go") and not path.is_symlink():
                self._add(path, cloud_cross_cutting_unit("cmd"))
        for root_name in ("runtime", "internal/platform"):
            for path in sorted((SERVICE_ROOT / root_name).rglob("*.go")):
                if not path.name.endswith("_test.go") and not path.is_symlink():
                    self._add(path, cloud_cross_cutting_unit("shared_runtime"))

        if not self.files_by_unit:
            raise CoverageError("Cloud 没有任何可计量的 production source unit")

    def _add(self, path: Path, unit: str) -> None:
        source = path.relative_to(SERVICE_ROOT).as_posix()
        previous = self.unit_of.get(source)
        if previous is not None and previous != unit:
            raise CoverageError(
                f"{_display(path)}: 同一 Cloud source 被归入多个 coverage unit: "
                f"{previous!r}, {unit!r}"
            )
        self.unit_of[source] = unit
        self.files_by_unit.setdefault(unit, set()).add(source)

    def canonical_source(self, coverprofile_source: str) -> str | None:
        """把 module/绝对 coverprofile path 规范为相对 ``quwoquan_service``。"""
        module_prefix = f"{SERVICE_ROOT.name}/"
        if coverprofile_source.startswith(module_prefix):
            relative = coverprofile_source[len(module_prefix) :]
        elif coverprofile_source in self.unit_of:
            relative = coverprofile_source
        else:
            candidate = Path(coverprofile_source)
            if not candidate.is_absolute():
                return None
            try:
                relative = (
                    candidate.resolve().relative_to(SERVICE_ROOT.resolve()).as_posix()
                )
            except ValueError:
                return None
        return relative if relative in self.unit_of else None


# ---------------------------------------------------------------------------
# 端侧归属（全部经 object_path_map，不写第二套规则）
# ---------------------------------------------------------------------------

LIB_PREFIX = "lib/"


class AppAttribution:
    """`lib/**` 生产文件 → canonical 对象/横切单元及磁盘文件名册。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        page_claims, pages = opm.load_page_claims()
        rows, _findings = opm.scan_app(roster, page_claims)
        self.unit_of: dict[str, str] = {}
        self.files_by_unit: dict[str, set[str]] = {}
        unowned: list[dict] = []
        repository_prefix = f"{opm.APP_LIB_ROOT.as_posix()}/"
        for row in rows:
            if row.get("role") != "production":
                continue
            path = str(row.get("path") or "")
            if not path.startswith(repository_prefix):
                raise CoverageError(
                    f"App production source path 非 canonical repo path: {path!r}"
                )
            library_relative = path[len(repository_prefix) :]
            object_id = str(row.get("objectId") or "")
            unit: str | None = None
            if object_id:
                record = roster.objects.get(object_id)
                if record is None:
                    raise CoverageError(
                        f"{path}: object_path_map 返回未知 objectId {object_id!r}"
                    )
                unit = app_object_unit(
                    record["domain"], record["context"], record["objectName"]
                )
            elif row.get("status") == "canonical_cross_cutting":
                root = str(row.get("crossCuttingRoot") or "")
                unit = app_cross_cutting_unit(root)
            else:
                unowned.append(row)
                continue
            previous = self.unit_of.get(library_relative)
            if previous is not None and previous != unit:
                raise CoverageError(
                    f"{path}: 同一 production source 被归入多个 coverage unit: "
                    f"{previous!r}, {unit!r}"
                )
            self.unit_of[library_relative] = unit
            self.files_by_unit.setdefault(unit, set()).add(library_relative)

        if unowned:
            examples = [
                (
                    f"{row.get('path')} "
                    f"(status={row.get('status')}, method={row.get('method')})"
                )
                for row in unowned[:20]
            ]
            suffix = (
                f"\n  ... 另有 {len(unowned) - len(examples)} 个"
                if len(unowned) > len(examples)
                else ""
            )
            raise CoverageError(
                "App production source 没有唯一 canonical object owner，且也不在 "
                "canonical cross-cutting root；必须先修归属，禁止登记 allowance：\n  "
                + "\n  ".join(examples)
                + suffix
            )
        missing_capability_units = sorted(
            set(expected_app_capability_units(roster, pages)) - set(self.files_by_unit)
        )
        if missing_capability_units:
            raise CoverageError(
                "App capability object 没有 owned production coverage unit；"
                "clientContract operation / canonical page owner 不能被空 baseline 放行：\n  "
                + "\n  ".join(missing_capability_units[:20])
                + (
                    f"\n  ... 另有 {len(missing_capability_units) - 20} 个"
                    if len(missing_capability_units) > 20
                    else ""
                )
            )
        if not self.files_by_unit:
            raise CoverageError("App 没有任何可计量的 production source unit")

    def known(self, source: str) -> bool:
        """lcov 的 `SF:` 路径是否属于本次派生覆盖到的 `lib/**` 生产文件。"""
        if not source.startswith(LIB_PREFIX):
            return False
        library_relative = source[len(LIB_PREFIX) :]
        return library_relative in self.unit_of


def _measure_app_unit(
    unit: str,
    lcov: dict[str, dict[str, tuple[int, int]]],
    attribution: AppAttribution,
) -> dict[str, dict]:
    try:
        on_disk = attribution.files_by_unit[unit]
    except KeyError as error:
        raise CoverageError(f"{unit}: 没有 production source 计量单元") from error
    reached = 0
    line_covered = line_total = 0
    branch_covered = branch_total = 0
    for source, values in lcov.items():
        library_relative = (
            source[len(LIB_PREFIX) :] if source.startswith(LIB_PREFIX) else source
        )
        if attribution.unit_of.get(library_relative) != unit:
            continue
        reached += 1
        line_covered += values["line"][0]
        line_total += values["line"][1]
        branch_covered += values["branch"][0]
        branch_total += values["branch"][1]
    return {
        "file": _metric(
            reached,
            len(on_disk),
            unmeasured_reason="该 App 单元在 lib/** 下没有任何生产文件",
        ),
        "line": _metric(
            line_covered,
            line_total,
            unmeasured_reason=(
                f"{APP_TEST_TARGET} 没有任何测试加载该 App 单元的 lib 文件"
                f"（磁盘 {len(on_disk)} 个，lcov 触达 {reached} 个）"
            ),
        ),
        "branch": _metric(
            branch_covered,
            branch_total,
            unmeasured_reason=(
                f"{APP_TEST_TARGET} 触达的该 App 单元文件里没有任何可判定分支"
                f"（磁盘 {len(on_disk)} 个，lcov 触达 {reached} 个）"
            ),
        ),
    }


def _measure_cloud_unit(
    unit: str,
    profiles: Sequence[tuple[str, dict[str, tuple[int, int]]]],
    attribution: CloudAttribution,
) -> dict[str, dict]:
    """只累计属于该 Cloud 对象/横切单元的逐文件 statement。"""
    covered = total = 0
    for target, files in profiles:
        unknown = sorted(
            source for source in files if attribution.canonical_source(source) is None
        )
        if unknown:
            raise CoverageError(
                f"{target}: coverprofile 含无 canonical 对象/横切 owner 的 source:\n  "
                + "\n  ".join(unknown[:20])
            )
        for source, (file_covered, file_total) in files.items():
            canonical = attribution.canonical_source(source)
            if canonical is not None and attribution.unit_of[canonical] == unit:
                covered += file_covered
                total += file_total
    if total <= 0:
        raise CoverageError(
            f"{unit}: statement 分母为 0；物理 source owner 与采集范围漂移"
        )
    if covered <= 0:
        raise CoverageError(
            f"{unit}: statement 实测 0/{total}；对象没有任何 production statement "
            "被 canonical local_contract 执行，禁止把 0% 登记成可准出基线"
        )
    return {"statement": _metric(covered, total, unmeasured_reason="")}


def _require_app_unit_measured(unit: str, metrics: dict[str, dict]) -> None:
    """App 任何不可测轴或 0/N 都不能进入 canonical baseline。"""
    failures: list[str] = []
    for metric in METRICS_BY_KIND[KIND_FLUTTER_LCOV]:
        entry = metrics[metric]
        if entry.get("status") == METRIC_STATUS_UNMEASURED:
            failures.append(f"{metric}=unmeasured ({entry.get('reason')})")
        elif int(entry.get("covered", 0)) <= 0:
            failures.append(f"{metric}=0/{entry.get('total')}")
    if failures:
        raise CoverageError(f"{unit}: App coverage 不可准出：" + "; ".join(failures))


def _metric(covered: int, total: int, *, unmeasured_reason: str) -> dict:
    """把 ``covered/total`` 折成 metric 条目；分母为 0 时如实标不可测，不写 0%。"""
    if total <= 0:
        return {"status": METRIC_STATUS_UNMEASURED, "reason": unmeasured_reason}
    return {"covered": covered, "total": total, "percent": percent(covered, total)}


def percent(covered: int, total: int) -> float:
    return round(covered * 100.0 / total, 2)


def _read_artifact(target: str) -> tuple[str, dict]:
    path = artifact_path(target)
    receipt = validate_artifact_receipt(target)
    return path.read_text(encoding="utf-8", errors="replace"), receipt


def measure(units: Sequence[str]) -> tuple[dict[str, dict[str, dict]], dict]:
    """读取落盘产物，折算成 ``{unit: {metric: entry}}`` 与全局附加事实。"""
    measured: dict[str, dict[str, dict]] = {}
    unit_receipts: dict[str, list[dict]] = {}
    app_units = [unit for unit in units if unit.startswith(APP_UNIT_PREFIX)]
    if app_units:
        attribution = cc.AppAttribution(_roster())
        app_text, app_receipt = cc._read_artifact(APP_COLLECTION_TARGET)
        lcov = cc.parse_lcov(app_text)
        unknown = sorted(source for source in lcov if not attribution.known(source))
        if unknown:
            raise CoverageError(
                "lcov 里有不属于当前 canonical 对象/横切单元的源文件"
                "（归属派生器与产物不同源）：\n  " + "\n  ".join(unknown[:20])
            )
        for unit in app_units:
            measured[unit] = _measure_app_unit(unit, lcov, attribution)
            _require_app_unit_measured(unit, measured[unit])
            unit_receipts[unit] = [app_receipt]

    cloud_units = [unit for unit in units if unit.startswith(CLOUD_UNIT_PREFIX)]
    if cloud_units:
        attribution = cc.CloudAttribution(_roster())
    for unit in cloud_units:
        profiles: list[tuple[str, dict[str, tuple[int, int]]]] = []
        receipts: list[dict] = []
        for target in cloud_collection_targets_for_unit(unit):
            artifact_text, receipt = cc._read_artifact(target)
            if _collection_target_language(target) == "python":
                files = parse_python_trace_files(artifact_text, target)
            else:
                files = parse_go_coverprofile_files(artifact_text)
            profiles.append((target, files))
            receipts.append(receipt)
        measured[unit] = _measure_cloud_unit(unit, profiles, attribution)
        unit_receipts[unit] = receipts
    return measured, {"unitReceipts": unit_receipts}
