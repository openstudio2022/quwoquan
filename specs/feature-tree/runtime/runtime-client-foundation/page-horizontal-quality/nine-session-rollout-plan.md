# 九会话横向落实规划（P1–P8 + 收口）

> **目标**：用 **9 个独立会话**，每次只攻 **一个横向维度**（或最终收口），对 [`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) 中 **全部页面行** 做 **检查 + 补齐 + 矩阵列更新**。  
> **真相源**：维度定义见 [`page-horizontal-quality-spec.md`](../page-horizontal-quality-spec.md)；置 ✓ 最低证据见 [`page_horizontal_quality_pr_checklist.md`](../../../../gates/page_horizontal_quality_pr_checklist.md) §各维。  
> **约束**：**P7（断点/版式）与 P8（语义 token）不得在同一会话混写收口**——对应 **会话 7** 与 **会话 8** 必须分开执行。

## 会话总览

| 会话 | 代号 | 横向焦点 | 矩阵列 | 本会话退出时矩阵状态 |
|------|------|-----------|--------|----------------------|
| **1** | S1 | iOS 原生根壳与材质 | **P1** | 凡适用页 P1 为 **✓** 或 **—**（— 须备注/allowlist） |
| **2** | S2 | 元数据驱动契约 | **P2** | 与 `metadata_driven_ui_gap_inventory.yaml` 的 `status` 对齐后可标 **✓**/ **—**/ **○** |
| **3** | S3 | 端云一体化（Repository 切换） | **P3** | 有云页 **✓**；无云页 **—** |
| **4** | S4 | 统一埋点 / 观测 | **P4** | 有管道或登记豁免；**—** 须备注 |
| **5** | S5 | 设置表单 / 对话态组件复用 | **P5** | 命中场景 **✓**；含 **`search_embedded`**（成员搜索壳）；不适用 **—** |
| **6** | S6 | 深色 / 浅色（S6） | **P6** | 与 `dual-theme-page-coverage` 矩阵交叉引用后可 **✓**/ **—** |
| **7** | S7 | 多屏断点与响应式布局（**仅 P7**） | **P7** | **默认策略 B**：`compact` / `regular` / `expanded` 全验收；`expanded` 优先 `feedMaxContentWidth` 等约束可读宽。版式达标或 **—**（取景区等须备注） |
| **8** | S8 | 设计系统语义 token（**仅 P8**） | **P8** | 与 `verify_dart_semantic` 等同向；无魔法数体系或 **—** |
| **9** | S9 | **收口验收** | **P1–P8 全列** | 发布口径下 **○ 仅允许带明确技术债条目**；跑通门禁 |

## 每会话标准工作流（复制到会话开场）

1. **拉齐枚举**：以 `page-horizontal-quality-matrix.md` 为工单，按领域分段；**不得漏行**（依赖 `scripts/verify_page_matrix_scan_complete.py` 与磁盘扫描一致）。  
2. **逐页**：打开对应 `lib/...` 文件 → 对照该维「置 ✓ 最低证据」→ 改代码或改 `metadata_driven_ui_gap_inventory` 等旁路真相源；**同步**按 [`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md) **§4.1** 检查 **业务与测试/夹具是否同文件混写**（有则迁出至 `test/`）。  
3. **回写矩阵**：只改 **当前会话负责的那一列**（收口会话 S9 可批量扫尾）。  
4. **本会话验证**（至少）：  
   ```bash
   python3 scripts/verify_page_horizontal_quality_matrix.py
   python3 scripts/verify_page_matrix_scan_complete.py
   python3 scripts/verify_ui_mock_isolation.py
   ```  
5. **涉及 P1**：额外 `python3 scripts/verify_ios_native_surface_gate.py`。  
6. **涉及 P5**：额外 `python3 scripts/verify_settings_canonical.py`、`python3 scripts/verify_conversation_sheet_canonical.py`（与变更相关则跑）。  
7. **涉及 P8**：关注 `python3 scripts/verify_dart_semantic.py`（在 `make gate` app 段中已串联）。

## 各会话范围与推荐顺序说明

- **顺序**：默认 **S1→S2→…→S8→S9**。若多人并行，**禁止** S7 与 S8 由同一人同一 PR 混写；**S9 必须最后**（全列一致性 + 债条登记）。  
- **S2**：逐页结论以 `specs/gates/metadata_driven_ui_gap_inventory.yaml` 为准；矩阵 P2 与清单 `status` 冲突时 **先改清单再改矩阵**。  
- **S4**：Tab 根可依托 `MainAppShell` pageAccess；独立路由页按统一观测方案补齐或标 **○** 并指向后续 Story。  
- **S9**：  
  - 全表扫描 **○**：须变为 **✓** 或 **—**，或在矩阵「备注」/ 兄弟 L3 中登记 **技术债 ID**；  
  - 执行 `make verify-app-page-horizontal-quality`（快检）与 `bash scripts/gate_repo.sh --scope app`（或完整 `make gate`，视 PR 范围）；  
  - **治理落盘**：Cursor 规则 `.cursor/rules/09-page-horizontal-quality.mdc`、`01-arch-constraints.mdc` §2.4、`page_horizontal_quality_pr_checklist.md` §S9；  
  - 更新 `specs/changelog/CR-*.yaml` 或在本 L3 `tasks.md` 勾选完成。

## 与会话规划相关的仓库产物

| 产物 | 说明 |
|------|------|
| 本文件 | 九会话 **唯一执行顺序与出口定义** |
| [`plan.yaml`](./plan.yaml) | `slice-3-nine-session-rollout` 指向本文件 |
| [`tasks.md`](./tasks.md) | M4 勾选 S1–S9；**M8** 勾选 **实施波次 B** |
| [`s2-metadata-driven-contract-baseline-20260330.md`](./s2-metadata-driven-contract-baseline-20260330.md) | **S2** 全页 P2↔清单对照表与基线锁定声明 |
| [`CR-20260329-006`](../../../../changelog/CR-20260329-006-page-horizontal-quality-nine-session-rollout.yaml) | 变更登记 |
| `plan.yaml` **slice-6** | `slice-6-mock-cloud-test-isolation-wave-b`（与 `acceptance.yaml` **A6** 同步；首 PR 实施时落盘） |
| [`CR-20260330-010`](../../../../changelog/CR-20260330-010-mock-isolation-implementation-wave.md) | 实施波次 B 登记（YAML 可与首 PR 补） |

---

## 实施波次 B：Mock · 端云 · 测试编译隔离（S1–S9 之后）

> **定位**：与 **横向维度 S1–S9**（P1–P8 矩阵列）**正交**；聚焦 **数据源真隔离**、**目录 §9**、**正式包零 Mock 耦合**。  
> **策略全文**：[`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md)（含 **§4.1** 同文件测试、**§9** 目录、`P0–P4` 阶段表）。  
> **变更登记**：**CR-20260330-010**（YAML 见 changelog，与实施首 PR 一并提交）。  
> **执行勾选**：[`tasks.md`](./tasks.md) **M8**。

### B0 脚手架（可首 PR 落地）

| 序号 | 任务 | 产出 |
|------|------|------|
| B0.1 | 建立 `quwoquan_app/test/support/`（`fakes/`、`fixtures/`、`harness/` 空目录 + README 说明引用策略 §9.2） | 目录 + 短 README |
| B0.2 | 建立 `quwoquan_app/lib/core/data_source/` 占位模块（`app_data_source_mode.dart` 从 `app_providers` **渐进**迁入） | 文件骨架 + 文档注记 |
| B0.3 | 选定 **首域试点**（建议 `chat`）：`remote/chat_repository_remote.dart` 与 `mock/` 并列路径（可与现有单文件 **渐进** 拆分） | 试点目录 |

### B1 清空 `ui_mock_isolation_allowlist`（与逐页矩阵并行）

按 [`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) **领域块** 迁移混入代码，每修一处 **删 allowlist 一行**：

| 策略阶段 | 内容 | 退出 |
|----------|------|------|
| **P0** | 维持 `verify_ui_mock_isolation.py`；**禁止** allowlist 新增行 | 新 PR 不扩大债 |
| **P0b** | `lib/**` 同文件测试/夹具迁 `test/support/`（§4.1） | 启发式门禁可选落地 |
| **P1** | UI/Core 去掉 `import .../mock/`；模型去掉 `prototype*` | allowlist **import_cloud_mock / embedded_prototype 清零** |
| **P2** | `RemoteAppContentRepository` 等 **不再** 全量委托 Mock | Remote 路径真 HTTP 或空态 |
| **P3** | `currentUserIdProvider` 等与 Auth 对齐 | `app_providers` 去掉 mock import |
| **P4** | `main_prod` / flavor；开发者数据源开关 **Release 不可见**；CI `--dart-define=APP_DATA_SOURCE=remote` | 商店包路径验收 |

### B2 每批验证（实施会话末尾必跑）

```bash
python3 scripts/verify_ui_mock_isolation.py
python3 scripts/verify_page_horizontal_quality_matrix.py
python3 scripts/verify_page_matrix_scan_complete.py
bash scripts/gate_repo.sh --scope app
```

### B3 矩阵 P3 与波次 B 的关系

- 每清完一批页面/横切文件：在矩阵 **备注** 中可标注 `wave-B` + CR；**P3** 在「无 UI 直连 mock、Remote 语义成立」后保持或更新为 **✓**。  
- **S3（P3）会话已勾选** 不豁免 **波次 B**：波次 B 解决的是 **架构债**（allowlist、伪 Remote、发行形态）。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-29 | 初版：S1–S9 规划冻结，供 9 个独立会话执行 |
| 2026-03-30 | 新增「实施波次 B」：Mock/端云/测试隔离 + B0–B3 与 CR-20260330-010 |

---

## 附录：实施首 PR 需合入的 YAML 片段（若仓库中尚未自动落盘）

> 以下供 **Agent 模式** 粘贴进 `plan.yaml` / `acceptance.yaml`；若已存在 **slice-6** / **A6** 则跳过。

**`plan.yaml`** 在 `slice-5-...` 块后追加：

```yaml
  - id: slice-6-mock-cloud-test-isolation-wave-b
    title: 实施波次 B（Mock·端云·测试编译隔离；policy §4.1 §9；清空 allowlist；prod 入口）
    outputs:
      - specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/nine-session-rollout-plan.md
      - specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/tasks.md
      - specs/gates/mock_data_cloud_integration_policy.md
      - specs/gates/ui_mock_isolation_allowlist.yaml
      - quwoquan_app/test/support/README.md
      - quwoquan_app/lib/core/data_source/
    tests:
      - python3 scripts/verify_ui_mock_isolation.py
      - bash scripts/gate_repo.sh --scope app
    dev_status: specified
```

**`acceptance.yaml`**：在 `A7` 与 `execution` 之间插入 **A6**；将 `execution.local_gate` 改为含 `verify_ui_mock_isolation.py`（见 [`acceptance.yaml`](./acceptance.yaml) 目标形态或本仓库已合并版本）。
