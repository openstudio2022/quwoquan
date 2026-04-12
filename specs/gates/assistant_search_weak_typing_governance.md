# 助手 / 模型 / App 搜索：弱类型棘轮门禁

## 1. 目标与边界

- **目标**：防止 **手写** 助手逻辑与 [`search_repository.dart`](../../quwoquan_app/lib/core/services/search_repository.dart) 在弱类型指标上**无记录回退**（`Map<String, dynamic>` 字面量与 `dynamic` 关键字计数上升）。
- **非目标**：**不**禁止 JSON 边界上的 `Object?`、**不**扫描 `*.g.dart`、**不**扫描 `lib/assistant/generated/**`（生成体由 metadata/codegen 演进）。
- **与页面门禁 C 的关系**：[`page_abc_governance.md`](page_abc_governance.md) 仅覆盖 **64 条页面路径** 的 `dynamic` / `Map<String, dynamic>` 字面量；**不包含** `lib/assistant/**` 全文。助手域弱类型由**本棘轮**与 [session_c_page_typing.md §1.1](session_c_page_typing.md) 原则共同约束。

### 1.1 诚信条款（防「指标游戏」）

本棘轮 **只检测回归**，**不等价于**「弱类型治理完成」或「类型安全提升」。

以下做法 **不得** 单独申报为弱类型收口的主要交付或「清零」：

- 将 **`dynamic` 改为 `Object?`**、将 **`.cast<String, dynamic>()` 改为 `.cast<String, Object?>()`** 等**仅关键字/字面替换**，而业务数据仍是 **Map 语义**、无 **metadata → codegen 具名 DTO** 或 **sealed 状态**。
- 以压低 `dynamic_keyword` 为唯一目标，却无 **契约变更**、无 **生成体替代手写 Map** 的 PR。

**诚实的收口**应以：**contracts/metadata 扩展 → `make codegen-app` → 手写层消费生成 DTO**（或明确的 sealed/domain 类型）为主路径；JSON 入口保留 `Object?` 仅作**解码边界**，不得冒充域模型已类型化。

评审可参考：[`assistant_weak_typing_review_checklist.md`](assistant_weak_typing_review_checklist.md)。

## 2. 策略选定（与规划一致）

| 方案 | 本仓库采用 |
|------|------------|
| A. 棘轮基线 | **已采用**：[`assistant_search_weak_typing_baseline.json`](assistant_search_weak_typing_baseline.json) |
| B. 窄路径增量 | 可选后续：对单个子目录加白名单/禁区时再补脚本 |
| C. Map 字面量 | **并入** bucket 指标 `map_string_dynamic`（与 [`report_map_typing_baseline.py`](../../scripts/report_map_typing_baseline.py) 同一正则口径） |

## 3. 扫描桶与指标

| Bucket | 路径 |
|--------|------|
| `assistant_handwritten` | `quwoquan_app/lib/assistant/**/*.dart`，排除 `**/assistant/generated/**` 与 `*.g.dart` |
| `core_search_repository` | `quwoquan_app/lib/core/services/search_repository.dart` |

每个 bucket 记录（**与基线比较、用于 CI 阻断**）：

- `map_string_dynamic`：`Map<String, dynamic>` 字面量出现次数（含空格变体）。
- `dynamic_keyword`：词边界 `\bdynamic\b` 出现次数。

**辅助信息（不参与回归比较）**：`--json` 可附带 `map_string_object_optional`（`Map<String, Object?>` 字面量计数），用于观察「弱 Map 形态是否从 dynamic 迁到 Object?」；**升高或降低均不单独作为质量结论**，避免与 §1.1 冲突。

## 4. 命令与 CI

```bash
# 与基线比较（回归则 exit 1）
python3 scripts/verify_assistant_search_weak_typing_ratchet.py

# 当前快照 JSON（含 buckets；可选 informational 辅助计数，见脚本 --json）
python3 scripts/verify_assistant_search_weak_typing_ratchet.py --json

# 有意放宽或收口后更新基线（应用专用提交说明）
python3 scripts/verify_assistant_search_weak_typing_ratchet.py --write-baseline
```

- **根门禁**：[`scripts/gate_repo.sh`](../../scripts/gate_repo.sh) 的 `run_app` 段在可用 `python3` 时执行本脚本。
- **Make**：`make verify-app-assistant-search-weak-typing-ratchet`（若已写入 [Makefile](../../Makefile)）。

## 5. 更新基线约定

仅在以下情况运行 `--write-baseline` 并提交 JSON：

- 经评审的弱类型**有意增加**（例如新工具文件），或
- 大规模收口后指标**下降**，需固定新底线。

禁止静默扩大指标：PR 应说明 bucket 与字段变化原因。
