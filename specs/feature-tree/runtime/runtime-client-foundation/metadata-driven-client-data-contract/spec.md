# L3：元数据驱动的客户端数据契约（metadata-driven-client-data-contract）

## 背景与动机

端侧存在 **UI 直接使用 `Map<String, dynamic>` 承载云契约**、**Mock 与 Remote 返回结构口头对齐** 等记录债，与仓库主线 **metadata-first → verify → codegen → Repository** 不一致，易导致字段漂移、双实现分叉及门禁难以自动化。

## 目标用户与目标

| 角色 | 目标 |
|------|------|
| 终端用户 | 与云侧字段、错误码一致的行为与展示，减少「Mock 正常、远端异常」类问题 |
| 开发者 | 新业务 **必须** 经元数据扩展；页面消费 **codegen 类型** 或经 metadata 注册的 ViewModel；Mock/Remote **同源实体** |
| 质量 / CI | 可通过 **缺口清单 + 后续门禁** 收敛存量面；新增违规可阻断 |

## 功能范围（In Scope）

1. **元数据驱动定义（契约层）**  
   - 领域字段、事件、错误码、API 路径与 operation 的 **唯一真相源** 为 `quwoquan_service/contracts/metadata/`（及 monorepo 内等价路径）。  
   - 客户端 DTO/常量/错误枚举以 **`make codegen-app`** 产物为准：`lib/cloud/runtime/generated/**`（及 `field_policy`、`error_codes` 等）。

2. **同源实体（Mock + Remote）**  
   - 同一 **Repository 抽象接口** 的 `Mock*` 与 `Remote*` 实现：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** Mock 返回「另一套 Map 键名」而 Remote 另一套。  
   - 过渡期允许在 Repository 内将 wire `Map` **仅作为反序列化输入**，边界外立即转为 codegen 类型再向上返回。

3. **页面消费约束（目标态）**  
   - `lib/ui/{domain}/pages/**` 中，**领域实体行数据**（会话、帖子、成员、圈子卡片等）应以 **codegen DTO / 基于 metadata 的 ViewModel** 进入 `build`，**禁止**长期以裸 `Map` 作为列表模型类型（见 `specs/gates/metadata_driven_ui_gap_inventory.yaml` 登记存量）。

4. **本 baseline 交付**  
   - 本 L3 的 **spec / design / acceptance / plan**、**缺口清单**、**CR**、**tree_index** 登记。  
   - **不**在本 baseline 会话内完成全仓库逐页改码；迁移按 `plan.yaml` 切片在独立 `/dev` 会话执行。

## Out of Scope

- 不在此一次性替换所有记录 `Map` UI（由缺口清单 + 分域切片消化）。  
- 不重新定义 Go 侧 EntityRegistry/拦截链（沿用现有 `quwoquan_service` 规则）。  
- **纯本地、无云契约** 的 UI 状态（如展开/折叠 flag）不要求 metadata。  
- **个人助理引擎** 内部 LLM 契约以 `lib/personal_assistant/contracts/` 为准，与本 L3「云 metadata」正交；若助理 **调用云 API**，仍须走 codegen Repository。

## 约束与对标

- 仓库规则：`metadata-first`、`04-fullstack-metadata-consistency`、Dart 侧 `PostBaseDto` 多态消费约束。  
- 与 `runtime-codegen` L2、`dart-semantic-gate` 互补：本 L3 强调 **UI↔Repository↔DTO↔metadata** 闭环与 **Mock/Remote 同源**。

## 覆盖矩阵

| 既有 Story | 关系 |
|------------|------|
| `entity-link-templates-metadata` | **可复制链接 / 深链** 结构以 `_shared/link_templates.yaml` 为单源，与 `app_routes` 显式绑定；详见同 L2 下该 L3 的 spec/design |
| `dart-semantic-gate` | 字面量与 import；本 L3 强调 **类型与契约来源** |
| `error-permission-display-semantics*` | 错误展示须消费 metadata 生成错误枚举 |
| `struct-repo-handler-migration-generation*` | 云侧生成链；本 L3 对齐 **端侧消费** |
| `page-horizontal-quality` | 横向维度 **P2** 与本 L3 同向；**逐页是否已收敛** 以 `specs/gates/metadata_driven_ui_gap_inventory.yaml` 的 `status` 为权威，横向矩阵 P2 列须与之对齐或可推导（见 `explore-baseline-readiness-20260329.md` §4-G1） |

## Explore / baseline 就绪分析

- **全页路径与清单对照、能否进入 baseline、Gap 与修改方案**：见同目录 [`explore-baseline-readiness-20260329.md`](./explore-baseline-readiness-20260329.md)。  
- **摘要**：规格类 baseline **可冻结**；**全页 UI 元数据消费闭环** 仍按 `plan.yaml` 切片推进；当前须优先消除 **横向矩阵 P2=✓** 与清单 **`partial`** 的语义冲突。

## 数据生命周期 / 权限

随各域 `fields.yaml` / 权限策略；本 L3 不新增业务权限，仅约束 **类型与来源**。

## 迁移与回滚

- **迁移**：按域将页面列表模型替换为 codegen DTO，同步更新 Mock/Remote；在缺口清单中将对应项标为 `compliant`。  
- **回滚**：若某域迁移失败，恢复代码并 **保留清单状态为 current_map**，不得删除 metadata 已存在字段。

## 验收重点摘要

- `spec.md` / `design.md` / `acceptance.yaml` / `plan.yaml` / `CR` / `metadata_driven_ui_gap_inventory.yaml` 已合入。  
- `tree_index.yaml` 已登记本 L3。  
- 新增云接口或新页面数据模型：**须** 先改 metadata 再 codegen，**禁止** 仅端侧手写 DTO 作为长期方案。

## L1 / L2 / L3 映射

| 层级 | 标识 |
|------|------|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `metadata-driven-client-data-contract` |
