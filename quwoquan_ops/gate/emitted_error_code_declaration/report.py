"""反向错误码治理门禁：实现发射了 stable code，但两个声明源都没有声明位。

现有契约校验（`quwoquan_service/internal/metadata/validate/governance_error.go`
的 `validateErrorGovernance`）两个循环都从声明出发：一个遍历 `Governance.Objects`
查 `emitted_by.operations`，一个遍历 `Operations` 把 `error_codes` 反查定义。
纯实现侧的事实既触不到 `CONTRACT.ERROR.UNKNOWN_OPERATION_CODE` 也触不到
`MISSING_OPERATION_EMISSION`，因此「实现了但契约没有声明位」这个方向没有任何
维度覆盖。本脚本补上这个方向。

判断放独立 verify 脚本而不是 validate 层：validate 的输入是 ContractGraph，
纯 metadata，没有源码树入口。把 Go 源码形态塞进去会让 `make verify-contract-graph`
的确定性依赖源码解析，不划算。

## 声明源（两个，都必须读）

1. 各对象 `quwoquan_service/**/contracts/**/errors.yaml`
2. `quwoquan_service/contracts/runtime_errors/errors/runtime_failure_codes.yaml`

## 声明形态（两种，都必须认）

块形态 `- code: X` 与 flow 形态 `- {code: X, kind: ...}`。仓内 668 个已声明码里
有 154 个只出现在 flow 形态；用 `^\\s*-?\\s*code:` 之类的行正则会把它们判成未声明，
这是本仓反复出现的假阳来源。所以声明侧一律用 YAML parser 解析，不用行正则。

## 发射形态

`EMISSION_FORMS` 同时覆盖 runtime `NewCode` 家族、生成的 `AppErrorFrom*`/`go_const`
调用、文件内局部构造器、跨包 config module 注入、领域 sentinel 到 handler factory
的映射，以及 App 生产 Dart 的 stable-code 发射。生成目录只用来确定 import target，
绝不把生成函数定义本身当成生产发射证据。

## 判据纪律

解析不出 module/kind 的发射位一律进 `unresolved_sites`，不做笛卡尔展开。
`writeRuntimeError` 那种 module/kind/reason 全是变量的站点，若按 file-wide 取值
集合做叉乘会从 6 个真实码变成 24 个组合码——那正是本仓要避免的弱判据。
未解析站点本身受基线管控：新增盲点同样 BLOCK，避免维度悄悄失去覆盖。

## 基线

历史只减不增基线已在 codes 与 unresolved_sites 同时清零后退休。默认文件缺席表示
严格零豁免：任何新未声明码或未解析站点都会直接 BLOCK，禁止重建空 policy 或把
declared-without-emission 债务吸收到反向基线。显式传入的迁移基线仍只接受精确
`MODULE.KIND.reason`，不接受通配符或 module 级批量豁免。

用法：
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py --report
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .baseline import _baseline_order_issues, _unresolved_key, load_baseline
from .constants import BASELINE_PATH, EMISSION_FORMS, ROOT
from .declarations import load_declarations
from .models import Emission, SOURCE_EVIDENCE_SURFACES
from .scan import scan_emissions
from .vocabulary import load_runtime_vocabulary


def evaluate(root: Path, baseline_path: Path) -> tuple[list[str], dict]:
    declarations, sources = load_declarations(root)
    declared = set(declarations)
    vocabulary = load_runtime_vocabulary(root)
    scan = scan_emissions(root, vocabulary, declarations)
    baseline = load_baseline(baseline_path)

    undeclared: dict[str, list[Emission]] = {}
    for emission in scan.emissions:
        if emission.code not in declared:
            undeclared.setdefault(emission.code, []).append(emission)

    failures: list[str] = []
    new_codes = sorted(code for code in undeclared if code not in baseline.codes)
    for code in new_codes:
        sites = undeclared[code]
        locations = sorted({f"{item.path}:{item.function}" for item in sites})
        failures.append(
            f"新增未声明错误码 {code}（{len(sites)} 处发射）：\n      "
            + "\n      ".join(locations)
            + "\n      修复：在所属对象 errors.yaml 声明该码（stable code / http_status /"
            " user_message / recovery.action / go_const / dart_const），或改用已声明码。"
        )

    emission_evidence_forms = {
        "runtime_new_code",
        "runtime_helper_ctor",
        "local_error_ctor",
        "config_module_ctor",
        "generated_app_error_factory",
        "go_const_identifier",
        "domain_sentinel_handler",
        "stable_code_literal",
        "app_stable_code_emission",
        "app_native_stable_code_emission",
        "app_generated_error_symbol",
        "python_stable_code_literal",
    }
    evidenced_codes = {
        emission.code
        for emission in scan.emissions
        if emission.form in emission_evidence_forms
    }
    declared_without_emission = sorted(
        code
        for code, owned in declarations.items()
        if any(SOURCE_EVIDENCE_SURFACES.intersection(item.surfaces) for item in owned)
        and code not in evidenced_codes
    )
    for code in declared_without_emission:
        owners = sorted({item.source_path for item in declarations[code]})
        failures.append(
            f"已声明错误码 {code} 的 emitted_by 包含可静态核验 surface，"
            "但生产源码没有发射证据：\n      "
            + "\n      ".join(owners)
            + "\n      修复：让真实 handler/App emission 使用 owner generated factory/"
            "stable code，或删除尚未实现的 emitted_by 声明；不得以 generated 定义"
            "本身充当发射证据。"
        )

    stale_codes = sorted(code for code in baseline.codes if code not in undeclared)
    for code in stale_codes:
        if code in declared:
            failures.append(
                f"基线条目 {code} 已经有声明位，必须从基线删除（基线只减不增，"
                "不留死豁免）。"
            )
        else:
            failures.append(
                f"基线条目 {code} 已不再被任何覆盖形态发射，必须从基线删除。"
                "若是改用了未覆盖的发射形态，请在同一轮登记新形态。"
            )

    scanned_unresolved = {
        _unresolved_key(site.path, site.expression): site for site in scan.unresolved
    }
    new_unresolved = sorted(key for key in scanned_unresolved if key not in baseline.unresolved)
    for key in new_unresolved:
        site = scanned_unresolved[key]
        failures.append(
            f"新增未解析发射位 {site.path}:{site.function} -> {site.expression}\n"
            "      该站点的 module/kind 不唯一，维度在此失去覆盖。修复：改成字面量"
            " module/kind，或在基线 unresolved_sites 登记并手工枚举它发射的码。"
        )

    stale_unresolved = sorted(
        key for key in baseline.unresolved if key not in scanned_unresolved
    )
    for path, expression in stale_unresolved:
        failures.append(
            f"基线 unresolved_sites 条目已消失，必须删除：{path} -> {expression}"
        )

    failures.extend(_baseline_order_issues(baseline_path))

    # 盲点内手工枚举出的未声明码：当前形态的扫描器无法重新推导它们，因此只报告、
    # 不阻断。把无法自动复核的手工事实做成阻断条件，等于把门禁绑在一份会腐烂的
    # 台账上——那是本仓已经吃过亏的形态。它们属于下一轮形态扩展的范围。
    blind_spot_undeclared: dict[str, list[str]] = {}
    for (path, _expression), entry in sorted(baseline.unresolved.items()):
        if (path, _expression) not in scanned_unresolved:
            continue
        for code in entry.get("emits") or []:
            if code not in declared and code not in undeclared:
                blind_spot_undeclared.setdefault(str(code), []).append(path)

    summary = {
        "declaration_sources": len(sources),
        "declared_codes": len(declared),
        "scanned_go_files": scan.scanned_files,
        "emissions": len(scan.emissions),
        "undeclared_codes": len(undeclared),
        "baselined_codes": sorted(code for code in undeclared if code in baseline.codes),
        "new_codes": new_codes,
        "unresolved_sites": len(scanned_unresolved),
        "new_unresolved_sites": len(new_unresolved),
        "blind_spot_undeclared": blind_spot_undeclared,
        "declared_without_emission": declared_without_emission,
        "emission_forms": {
            form: sum(1 for item in scan.emissions if item.form == form)
            for form in EMISSION_FORMS
        },
        "undeclared_detail": {
            code: sorted({f"{item.path}:{item.function}" for item in sites})
            for code, sites in sorted(undeclared.items())
        },
    }
    return failures, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument(
        "--report",
        action="store_true",
        help="打印全部未声明码与发射位，用于维护基线",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline).resolve()

    failures, summary = evaluate(root, baseline_path)

    print("[emitted-error-code] 反向维度：实现发射但契约无声明位")
    print(f"  覆盖发射形态：{', '.join(EMISSION_FORMS)}")
    print(
        f"  声明源 {summary['declaration_sources']} 个，"
        f"已声明码 {summary['declared_codes']} 个"
    )
    print(
        f"  扫描 Go 文件 {summary['scanned_go_files']} 个，"
        f"解析出发射 {summary['emissions']} 处"
    )
    print(
        f"  未声明码 {summary['undeclared_codes']} 个："
        f"已在基线内 {len(summary['baselined_codes'])} 个，"
        f"新增 {len(summary['new_codes'])} 个"
    )
    print(
        f"  未解析发射位（维度盲点）{summary['unresolved_sites']} 处："
        f"新增 {summary['new_unresolved_sites']} 处"
    )
    print(
        "  可静态核验 emitted_by 但无生产发射证据 "
        f"{len(summary['declared_without_emission'])} 个"
    )
    print(
        "  各形态证据："
        + ", ".join(
            f"{form}={count}"
            for form, count in summary["emission_forms"].items()
        )
    )
    blind_spot = summary["blind_spot_undeclared"]
    print(
        f"  盲点内手工枚举出的未声明码 {len(blind_spot)} 个（只报告不阻断，"
        "属下一轮形态扩展范围）"
    )
    for code, paths in sorted(blind_spot.items()):
        print(f"      {code}  <- {', '.join(sorted(set(paths)))}")
    print(
        f"  未声明码合计（当前形态 {summary['undeclared_codes']} +"
        f" 盲点手工 {len(blind_spot)}）= "
        f"{summary['undeclared_codes'] + len(blind_spot)}"
    )

    if args.report:
        print("\n  == 未声明码明细 ==")
        for code, locations in summary["undeclared_detail"].items():
            marker = "baselined" if code in summary["baselined_codes"] else "NEW"
            print(f"  [{marker}] {code}")
            for location in locations:
                print(f"        {location}")
        print("\n  == 已声明但无生产发射证据 ==")
        for code in summary["declared_without_emission"]:
            print(f"  {code}")

    if failures:
        print("\n[emitted-error-code] FAIL")
        for index, failure in enumerate(failures, start=1):
            print(f"  {index}. {failure}")
        return 1
    print("[emitted-error-code] OK")
    return 0
