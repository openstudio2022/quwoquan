# design：metadata-driven-client-data-contract

## 1. 核心原则

1. **单一真相源**：`contracts/metadata` → `make verify-metadata` / `make codegen-app` → `lib/cloud/runtime/generated/**`。  
2. **边界收口**：HTTP/Mock 边界在 **Repository 实现**；出 Repository 的「领域载荷」优先为 **codegen 类型**（或明确标注的、由 codegen 字段组成的不可变 ViewModel，且字段名与 metadata 一致）。  
3. **Mock ≡ Remote 类型**：`MockXxxRepository` 与 `RemoteXxxRepository` 实现同一 `XxxRepository` 抽象；同一方法返回类型 **完全相同**；Mock 数据通过 `XxxDto.fromMap` 或 `const XxxDto(...)` 构造，与 Remote 解析路径一致。  
4. **UI 层**：列表/详情 **禁止** 以 `List<Map<String,dynamic>>` 作为 **会话、帖子、成员、圈子实体** 的常驻状态类型（过渡期见缺口清单）。

## 2. 与 Provider 的关系

- `app_providers` / `appDataSourceModeProvider` 仅切换 **实现类**，**不**切换返回类型签名。  
- `Ref.read(xxxRepositoryProvider)` 对业务代码透明；Mock/Remote 返回同一抽象上的同一具体类型（或 sealed/union 的 codegen 分支，由 metadata 驱动）。

## 3. 缺口清单（`metadata_driven_ui_gap_inventory.yaml`）

- **domain**：对齐 `contracts/metadata` 或 `lib/cloud/services/{domain}`。  
- **status**：  
  - `compliant`：该域列表/核心页已以 codegen DTO 为主链路。  
  - `partial`：Repository 已类型化，UI 仍部分 Map。  
  - `legacy_map`：UI 或 Mock 仍以 Map 为主。  
- **target_dto**：指向 `generated` 中已有或待补的 codegen 类名（或 `TBD`）。  
- 清单 **允许收缩**：迁移完成后项改为 `compliant` 或可删除；**新增**遗留须登记并附原因/切片号。

## 4. 后续门禁（plan 中实现，非本 baseline 必交付）

- 可选脚本：对 `lib/ui/**/pages/*.dart` 扫描 `List<Map<String, dynamic>>` 与特定 Provider 类型，**仅阻断新增**（基线比对），或按域启用。  
- 与 `make gate` 集成方式同 `verify_ios_native_surface_gate.py`。

## 5. 多态与 content

- Feed/帖子遵循 **`PostBaseDto` 子类** 与仓库规则：**禁止** UI 用 `is`/`as` 判型；差异收口到基类能力位。  
- metadata 新增 post 子类型时：**先** 扩展 `fields.yaml` / codegen，**再** 扩展 `postBaseDtoFromMap` 分发。

## 6. 风险

- 大范围改状态类型会引发 **大范围 diff**；必须按域切片、每切片 `flutter analyze` + 契约测试。  
- 部分页面仍依赖 `DataService` 遗留 Map：须在清单中单列 **deprecate_path**，避免与 Repository 双源。
