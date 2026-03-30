# design：S8 — P8 语义 token 落实

## 上游规格评审

- [`spec.md`](./spec.md) 已冻结范围、12 页优先清单、P7/P8 分离、无 metadata。  
- 与父 L3 `page-horizontal-quality`、九会话规划 **S8** 一致。

## 方案对比与选型结论

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 波次删 baseline + token 替换** | 按 W0→W5 推进；改代码即删 `baseline.txt` 对应行 | **选用** |
| **B. 放宽门禁规则** | 扩大 regex 豁免，债务隐藏 | **不采纳** |
| **C. 仅文档登记 ✓** | 无代码与 baseline 变化 | **不采纳** |

## metadata / codegen

**不适用**（无 `make codegen-app` 变更）。

## 字段演进 / 迁移 / 双写

不适用。

## feature flag / 观测 / SLO

- **无 feature flag**。  
- **观测**：PR 中 `baseline.txt` 行数 diff；矩阵 P8 **✓/○** 比例。  
- **SLO**：治理型 L3，不单独承诺线上 KPI（见父 spec 商用基线）。

## 波次实施设计（与 `plan.yaml` 对齐）

| 波次 | 内容 | 退出条件 |
|------|------|-----------|
| **W0** | 盘点重复数字 → `AppSpacing` 扩展或域内 `*_layout_constants.dart` | 新代码不引入未命名字面量 |
| **W1** | **12 个 baseline 页文件** 逐文件清零（或合法 ignore） | 这些路径从 baseline 移除 |
| **W2** | 创作链：`create_page`、`video_editor`、`ios_article_editor`、`article_detail` 及强相关 widgets | baseline 相关行减；矩阵备注更新 |
| **W3** | 助手消息 UI baseline 簇 | 同上 |
| **W4** | 媒体全屏 viewer / editor 子面板 | 工具 UI 常量成组命名 |
| **W5** | 其余 baseline + 矩阵页抽检 | baseline 仅余登记豁免 |

## 与 `verify_dart_semantic` 的关系

- **PATTERNS**：`width`/`height`/`fontSize`/`EdgeInsets`/`BorderRadius.circular`/`Color(0x` 等 — **P8 主战场**。  
- **GLOBAL_BANS**（Material Scaffold 等）：与 **P1** 重叠；S8 PR **若仅改 token** 应避免触动根壳；若同文件必须修，在 PR 描述中 **显式标注 P1 顺带**。  
- **inline ignore**：仅当第三方/不可改约束时使用，且 **单行 + 注释原因**。

## T1–T4 证据矩阵（本 L3）

| 层 | 证据 |
|----|------|
| **T1** | 本 `spec.md`、`design.md`、`acceptance.yaml`、`CR-20260330-012` |
| **T2** | `verify_dart_semantic.py`、`verify_page_horizontal_quality_matrix.py`、`verify_page_matrix_scan_complete.py` |
| **T3** | PR：baseline diff + 矩阵 P8 行 diff |
| **T4** | 全量 baseline 收敛目标：随 W5 结束或登记「剩余债」至矩阵备注 / 技术债 ID |

## 回滚

revert 波次 PR；必要时恢复 `baseline.txt` 历史版本以恢复 gate 绿。
