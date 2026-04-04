# 页面 A/B/C 治理规范与门禁

## 1. 适用范围（规范性）

扫描路径集合与 [`scripts/verify_page_matrix_scan_complete.py`](../../scripts/verify_page_matrix_scan_complete.py) **磁盘集完全一致**，由 [`scripts/page_disk_scan_paths.py`](../../scripts/page_disk_scan_paths.py) 唯一枚举（修改规则时只改该模块，避免与矩阵脚本漂移）。

**包含**（`quwoquan_app/` 相对路径）：

- `lib/ui/**/pages/*_page.dart`（排除占位 `lib/ui/chat/pages/chat_display_fallbacks.dart`）
- `lib/ui/welcome/pages/welcome_screen.dart`
- `lib/components/**/*_page.dart`
- `lib/app/shell/*.dart`

**不包含**：`lib/cloud/runtime/models/cursor_page.dart` 等未纳入横向矩阵扫描基线的文件。

**非页面代码**：本门禁**仅**扫描上述路径；`create_editor_models.dart`、Remote Repository 等由会话 A/B/C 另行清理，但不在本脚本计数范围内。

## 2. 维度定义

| 维度 | 含义 |
|------|------|
| **A** | 版本分叉与代际命名：`draftVersion`、`_fromV2*` / `_fromLegacy*`、`version=='vN'`、`RewriteV2`、`uiProcessTimelineV2`、注释「V2 原型」「发现页 V1」等（与脚本内 `A_PATTERNS` 一致）。 |
| **B** | 业务 Legacy 标识：`Legacy*` 类名、`legacyPageId`、`fromLegacy*`、`onOpenLegacy*` 等（与脚本内 `B_BAD_PATTERNS` 一致）。 |
| **C** | 文件内 `dynamic` 关键字与 `Map<String, dynamic>` 出现；`enforce-c` 要求二者合计为 **0**（除非白名单豁免）。 |

**会话 C 数据驱动收口**：browse/open/return 等 page_access 载荷须使用 [ops/event_record/projections/](../../../quwoquan_service/contracts/metadata/ops/event_record/projections/) 中 `app_log_*.yaml` 经 `make codegen-app` 生成的 DTO（`.toMap()` 仅在生成体内），详见 [session_c_page_typing.md](session_c_page_typing.md)。

**Riverpod 官方子库**：`import 'package:flutter_riverpod/legacy.dart'` **不计入** B 违规，仅作信息行 `B~`；**不**触发 `--enforce-b`。

## 3. 门禁分级与退出码

| 模式 | 行为 | 退出码 |
|------|------|--------|
| 默认（无 `--enforce-*`） | 打印命中与汇总；未豁免违规**不**导致失败 | `0` |
| `--enforce-a` / `--enforce-b` / `--enforce-c` | 对应维度存在**未豁免**违规则失败 | `1` |
| 工具/配置错误（无 `quwoquan_app/lib`、白名单 `path` 不在 64 集、互斥输出参数、显式 `--allowlist` 指向缺失文件等） | 报错 | `2` |

**输出模式**（互斥）：默认详细列表、`--quiet` / `--summary-only`（单行汇总）、`--markdown`（表格）、`--json`（机器可读）。

## 4. 白名单（allowlist）

默认文件：[`page_abc_governance_allowlist.yaml`](page_abc_governance_allowlist.yaml)（仓库根相对：`specs/gates/page_abc_governance_allowlist.yaml`）。

**根结构**：

```yaml
exemptions:
  - path: lib/ui/example/pages/example_page.dart   # quwoquan_app 相对，须在 64 路径内
    dimensions: [A, C]                             # 大写 A / B / C，至少一项
    reason: "必填：豁免原因"
    tracking: "可选：CR-xxxx 或 issue"
```

**规则**：

- `path` 不在矩阵扫描集内 → 脚本 **失败（exit 2）**，防止写错路径。
- 未知键 → 打印 `WARN` 到 stderr，不失败。
- **禁止**无跟踪信息的长期豁免；收口后应删除对应条目。

自定义路径：`python3 scripts/verify_page_abc_governance.py --allowlist /path/to.yaml`。

## 5. 与横向矩阵门禁的关系

本脚本 **不替代**：

- `python3 scripts/verify_page_horizontal_quality_matrix.py`
- `python3 scripts/verify_page_matrix_scan_complete.py`

**建议顺序**：矩阵与漏扫通过后，再执行页面 A/B/C 扫描（`gate_repo.sh` 中物理顺序一致）。

## 6. 工具命令

```bash
# 详细报告（成功退出，即使有未豁免项）
python3 scripts/verify_page_abc_governance.py

# 单行汇总（适合 CI 日志）
python3 scripts/verify_page_abc_governance.py --quiet

# Markdown / JSON
python3 scripts/verify_page_abc_governance.py --markdown
python3 scripts/verify_page_abc_governance.py --json

# 收口（按阶段打开；须配合代码清理或白名单）
python3 scripts/verify_page_abc_governance.py --enforce-a --enforce-b
python3 scripts/verify_page_abc_governance.py --enforce-a --enforce-b --enforce-c
```

**Make**：

- `make verify-app-page-abc-governance` — 默认详细报告，`exit 0`。
- `make verify-app-page-abc-governance-enforce-a`（及 `b` / `c` / `all`）— 见根 [`Makefile`](../../Makefile)。

## 7. CI / `gate_repo.sh` 约定

环境变量 **`GATE_PAGE_ABC_ENFORCE`**（可选）：

- 未设置或为空：在 `run_app` 中执行 `verify_page_abc_governance.py --quiet`，**不阻断** gate（仅汇总一行）。
- 已设置：按令牌追加 `--enforce-*`，命中未豁免违规则 **阻断** gate。

**令牌**（不区分大小写，可组合，逗号或空格分隔）：`a`、`b`、`c`、`ab`、`bc`、`ac`、`abc`（或 `a,b,c`）。示例：

```bash
export GATE_PAGE_ABC_ENFORCE=a
bash scripts/gate_repo.sh --scope app

export GATE_PAGE_ABC_ENFORCE=abc
bash scripts/gate_repo.sh --scope app
```

**注意**：当前仓库在 **C** 维度上多有页面未清零，**勿**在全员 gate 上默认 `GATE_PAGE_ABC_ENFORCE=c` 或 `abc`，除非已清债或已填白名单。

## 8. A — 版本分叉与代际命名（目标说明）

**目标**：业务与持久化不再保留 `v1`/`v2`/`draftVersion` 多路读写；方法名不出现 `_fromV2Map`、`_fromLegacyMap` 等。

**说明**：不在 64 页面文件内的存储模型（如 `create_editor_models.dart`）由 **会话 A** 清理；页面文件内命中由本脚本 **A** 维度报告。

## 9. B — Legacy 业务语义（目标说明）

**目标**：自研代码中类名/方法名/字段名不出现 `Legacy` 承载的兼容分支语义；`legacyPageId` 等应迁移为与 metadata 一致的命名（并走 codegen）。

**仍算违规（页面内，摘要）**：`onOpenLegacyTab`、`_LegacyFallbackSheet`、`fromLegacyScope` 等（以脚本正则为准）。

## 10. C — dynamic 与 Map&lt;String, dynamic&gt;（目标说明）

**目标**：页面内裸 `dynamic`、`Map<String, dynamic>` 逐步替换为 **metadata → codegen** 的 DTO、或经 spec 标注的 **UI-only 不可变模型**（见 [session_c_page_typing.md](session_c_page_typing.md) §1.1）。**不得**用 `Object?` / `Map<String, Object?>` 在页面层冒充契约类型。

**门禁与目标**：脚本只匹配字面量 `dynamic` 与 `Map<String, dynamic>`；清零 C 是必要条件，**充分条件**仍是「字段与 metadata 一致、调用方持生成/明确类型」。

**常见牵引文件（非页面）**：

- `lib/ui/content/entry/models/create_editor_models.dart`
- `lib/cloud/services/**/remote/*_repository.dart`
- `lib/core/providers/app_providers.dart`

## 11. 四会话分工（复制用）

| 会话 | 职责 |
|------|------|
| **A** | 清版本分叉与代际命名（含非页面模型、助手协议键若需改 metadata） |
| **B** | 清业务 Legacy 标识与兼容路径（Repository / Widget / 常量；`legacyPageId` 与 codegen 对齐） |
| **C** | metadata/codegen 强类型化 + 页面/Provider 去 `dynamic` |
| **D（本规范）** | 维护本文档、`page_abc_governance_allowlist.yaml`、`verify_page_abc_governance.py`、`page_disk_scan_paths.py`、gate/Make 串联 |
