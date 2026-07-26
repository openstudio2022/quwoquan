# L3 Story：领域服务目录与 L1 归属 (`domain-service-directory-ownership`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为所有 Scenario 提供可定位的领域服务实现边界
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为维护服务契约与实现的开发者，我希望从每个服务自身的 `contracts/domain.yaml` 和 L1 工程归属直接定位唯一责任领域，从而在移动对象目录、生成物或环境入口时不依赖服务名册或宽泛 fallback 猜测 owner。

## 2. 范围与非目标

### In Scope

- 从 `services/*/contracts/domain.yaml` 动态发现领域服务根。
- 每个发现的服务根由一个非宽泛 fallback 的 L1 `Service` 工程归属直接拥有。
- `_shared` 跨服务 metadata 由 runtime L1 拥有，业务 L1 只作为协作消费者引用。

### Out of Scope

- 改变业务对象的公开 wire、operation 或错误语义。
- 建立服务注册表、路径映射表或人工领域名册。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 服务根从本地契约和 L1 归属唯一反推

- 领域服务只由存在 `contracts/domain.yaml` 的物理服务根发现。
- 每个发现的服务根必须被恰好一个 L1 的直接 `Service` 根认领；`quwoquan_service` 等宽泛根不得代替业务领域 owner。
- 服务迁移、新增或删除后，归属结论必须由当前目录和 L1 spec 重算，不维护固定服务数量或名称清单。

<a id="req-002"></a>
### REQ-002 跨服务 metadata 与业务服务归属分离

- `contracts/metadata/_shared` 由 runtime 作为跨服务契约基础设施拥有。
- 业务 L1 对共享 metadata、跨域服务或嵌套实现路径只能声明协作引用，不得借此覆盖服务根 owner。

## 4. 契约引用

- canonical：`quwoquan_service/services/*/contracts/domain.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared`
- scanner：`quwoquan_ops/cli/feature_tree.py`
- service gate：`quwoquan_ops/gate/verify_service_architecture.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 物理服务根具有唯一业务 L1 owner

- GIVEN 仓库中存在带 `contracts/domain.yaml` 的服务根和 L1 工程归属。
- WHEN 特性树门禁扫描当前服务目录与 L1 spec。
- THEN 每个服务根均由恰好一个直接 `Service` 根认领，且不能只解析为宽泛 fallback。

<a id="gwt-002"></a>
### GWT-002 共享 metadata 与服务集合不依赖人工名册

- GIVEN 跨服务 metadata 和服务本地 contracts 同时存在。
- WHEN 目录门禁重建服务与工程归属。
- THEN `_shared` 的 owner 为 runtime，服务集合由 `contracts/domain.yaml` 发现，新增合规服务不需要更新固定服务名册。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的目录、契约与服务自治边界。
- 上游事实：L1 工程归属、服务本地 `contracts/domain.yaml` 与共享 metadata 目录。
- 下游结果：唯一领域 owner 或 `GATE_BLOCK`。
- 父级设计：`DEC-001`
