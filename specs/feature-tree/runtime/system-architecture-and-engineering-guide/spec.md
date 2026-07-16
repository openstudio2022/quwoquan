# L2 特性：system-architecture-and-engineering-guide

## 功能说明

本节点冻结端云系统架构与工程阅读导引，作为研发、Agent、部署与验收进入云侧工作的统一入口。它不复制部署拓扑数据，而是链接现有唯一真相源，并补齐“服务目录、部署进程、能力现状、gap 与可拆分边界”之间的解释层。

## 背景问题

当前仓库存在多套相近但语义不同的清单：

- `quwoquan_service/services/*` 表示源码服务目录。
- `cmd/*/main.go` 表示可执行入口，一个服务可能有多个入口。
- `quwoquan_ops/environments/process_domain_mapping.yaml` 表示部署进程到 domain 的归属。
- `quwoquan_ops/environments/workload_topology_inventory.yaml` 表示 workload 三态与 prod wiring。
- `quwoquan_ops/environments/module_package_mapping.yaml` 表示部署包承载哪些 runtime module。

缺少“先读这个”的统一导引时，很容易把上述清单混数为“29+ 个服务”，或把部署进程名误认为源码目录名。本节点将这种漂移收口为可校验的工程契约。

## 产品目标

- 让端云闭环（内容工程生产 → App 展示 → 交集 → 行动 → 回流）在商业化冷启动阶段有一条可读、可验证、可部署的主路径。
- 让冷启动部署优先采用 `seed-box` 模块化单体，降低早期复杂度与成本，同时让管理/运营/运维面独立发布，保留 Strangler Fig 按域拆分能力。
- 让任何研发或 Agent 能从本节点快速定位：服务在哪里、职责是什么、当前能力做到哪里、gap 在哪里、该跑哪些门禁。

## 范围

### In Scope

- 端云服务目录、部署进程、runtime module、存储依赖与平面归属的解释导引。
- `seed-box` one-box 与 standalone workload 的边界说明。
- `Data -> Service -> App -> Behavior -> Recommendation -> Observability -> Environment` 闭环能力现状与 gap 矩阵。
- 与本节点相关的现有文档收编：陈旧服务层文档改为历史参考，权威入口指向本节点。
- 验收和门禁：feature-tree schema、部署拓扑门禁、Strangler 不变量、gamma-local/prod 同构。
- D0 业务对象边界、Object Facade、统一 URL、Data Ports、页面 Slice、错误与测试合同。
- F1 唯一 ContractGraph compiler、最小 Runtime/App 公共底座和 Actor/Operation attribution。
- G1 metadata/codegen、DDD、页面、测试、生产纯净、覆盖与零兼容清理硬门禁。
- 首个 `content-service` Post+Report 样板及样板后 scaffold 反证顺序。
- App Cloud 只消费 ContractGraph 的 generated client/typed contract，按
  runtime、remote adapter、application、local infrastructure、platform 与 composition
  root 分层；Mock/fixture 与 production 物理隔离。
- 服务目录按源码、部署包、外部工作负载和静态发布物分类，并验证
  domain/source/module/package/process/workload/capability 的双向闭包。

### Out Of Scope

- 替代 `quwoquan_ops/environments/*.yaml` 成为第二套拓扑真相源。
- 替代 `quwoquan_service/contracts/metadata/**` 成为 API path / operation / surface / route 真相源。
- 具体业务功能实现（交集算法、推荐策略、数据工程内容生产等）本身；本节点只描述其端到端承载路径和 gap。
- edge-media 的详细 RTC/SFU/TURN 实现。
- 为各领域生成万能 Repository/BaseFacade/Page，或在首个样板前预先提炼业务 scaffold。
- 在 App Cloud 或服务目录治理中重新裁决 aggregate、Facade、Reader/Slice、业务 operation
  或 store 语义；这些仍由业务对象 metadata 与对应领域会话唯一负责。

## 商用工程准入顺序

```text
D0 设计冻结
  -> F1 ContractGraph + 最小公共底座
  -> G1 硬门禁与旧模式冻结
  -> content-service Post + Report 样板
  -> Mongo + PostgreSQL 双 adapter 反证
  -> scaffold / 对象会话模板
  -> 其余业务对象波次
  -> 十条 AppRoot Journey + Data/Deploy SIT
```

- D0 未通过不得写样板业务代码。
- 样板未通过不得向其他对象复制 Facade/Store 模式。
- 双 adapter 与第二真实对象未反证前不得发布 scaffold。
- 当前阶段允许全面重构，禁止以兼容、Deprecated、allowlist、动态 skip 或 Memory/Noop 路径延长旧实现。

## 权威真相源

本节点只链接和解释以下真相源，不复制其内容：

- `quwoquan_ops/environments/process_domain_mapping.yaml`：domain 归属唯一真相源。
- `quwoquan_ops/environments/process_domain_plane_mapping.yaml`：domain-plane 归属。
- `quwoquan_ops/environments/workload_topology_inventory.yaml`：workload 三态、prod wiring、split candidates。
- `quwoquan_ops/environments/module_package_mapping.yaml`：部署包到 runtime module 的映射。
- `quwoquan_ops/environments/reliable_task_module_catalog.yaml`：runtime module 能力、队列、store 与 one-box/standalone 约束。
- `quwoquan_service/contracts/metadata/**/service.yaml`：API path、operation、domain 的唯一真相源。
- `specs/feature-tree/tree_index.yaml`：特性树索引。

## 运行输出边界

- `.qwq_output/` 是 disposable output root，只保存运行过程、派生发布包、观测证据和可重建缓存，不保存静态配置或可复用工程输入。
- App、Service、Data、Ops 的配置、schema、prompt、template、policy、reference、依赖声明和构建规则必须由各自领域源码目录拥有。
- 删除 `.qwq_output/` 不得破坏仓库的构建定义；后续执行只能从版本控制真相源或显式外部系统重建，不能把前一次 output 当成唯一输入。
- 部署可以消费本次构建产生的 release package，验证可以消费本次运行证据；这种阶段间派生消费不改变 output 的可删除属性。

## 当前服务目录与部署进程口径

服务数量和成员不得在本文复制。机器真相来自 ContractGraph、process/module/workload
清单与源码目录扫描；本文只冻结资产类型：

- `go-domain-source`：第一方 Go 领域源码与编译边界。
- `go-control-plane-source`：第一方 Go 控制面源码。
- `python-domain-source`：Python 模型/领域源码与 build context。
- `deployment-package`：只组合 runtime module，例如 `seed-box`。
- `external-workload`：受控外部镜像能力，例如 SFU/TURN。
- `static-artifact`：静态发布物，例如 legal-static。

必须区分 domain、source service、runtime module、deployment package、OS process、
workload 与 external capability。部署进程名不等于源码目录名；缺 source/build
provenance 的 workload 必须阻断，不能靠目录名推断。

## one-box 冷启动目标

商业化冷启动阶段默认采用：

- application plane：`seed-box` 是 deployment package/workload；实际成员只能从
  `process_domain_mapping` 与 `module_package_mapping` 推导，并必须与 Docker build
  列表和 supervisor `SERVICE_SPECS` 完全一致。
- management / product-ops plane：`product-ops-service` 独立 workload/package，承载 `ops` domain、`/v1/ops*` 与 `/v1/control-plane/product*`，不再作为 `seed-box` 子进程。
- recommendation：保留独立 `recommendation-service`（Python 打分），但可在冷启动关闭；规则推荐与交集在 `content-service` 进程内运行。
- search：保留独立 `search-service` 作为 ES 读模型与 `/v1/search*` 上游；冷启动可按 ES 是否可用决定启用。
- edge-media：`realtime-gateway`、`rtc-service`、`livekit-sfu`、`coturn` 从第一天独立，不并入 `seed-box`。
- 数据面：MongoDB、Redis scenes、Postgres、ES/OpenSearch 外置，通过 env/config 注入，允许共享或按域拆分。
- prod-hosted 运行时四平面继续以 `edge`、`media`、`service`、`data` 为访问隔离真相源；其中 `service` 平面内的发布工作负载必须至少包含 `seed-box`、`recommendation-service`、`product-ops-service` 三个独立 release unit。

## 闭环能力现状与 gap 矩阵

| 闭环阶段 | 当前承载 | 状态 | 主要 gap | 验收证据 |
|---|---|---|---|---|
| 内容工程冷启动生产 | `quwoquan_data` + metadata fixtures + seed manifests | 部分 | 数据工程脚本实现深度需继续按真实文件与产物核验；锚点到内容/实体/用户的灌数链需完整 T3 证据 | data CLI gate、content seed manifest、gamma seed 报告 |
| 内容入库与展示 | `content-service`、App content/discovery UI | 部分 | 大规模内容入库、媒体安全、search/location/tag 回填需持续验证 | content local_contract/api_integration、App user_acceptance |
| 标签/实体锚点 | `tag-service`、`entity-service`、`search-service` | 部分 | 需在 one-box 中真实承载 tag/entity，并保证 `/v1/homepages`、`/v1/tag` 路由可达 | tag/entity contract、search projection tests |
| 推荐与交集生成 | `content-service` 进程内 `runtime/recommendation` + `IntersectionService` | 部分 | 交集到行动闭环需持续补行为回流与行动完成证据 | intersection local_contract + content-service tests |
| 行动承接 | App object page / companion action / chat/user/circle | 部分 | 约伴、关注、私信、群/圈加入等行动链路需按 CDE 分批补 UAT | App widget/user_acceptance |
| 回流与观测 | behavior、recommend feature、`product-ops-service` metrics | 部分 | 行动完成数/关系形成数 North Star 的统一指标与 dashboard 仍需接 product-ops | runtime/ops acceptance + metrics gate |
| 环境与部署 | `seed-box` + `product-ops-service` + standalone workloads + stackctl | 部分 | 拓扑 SSOT 与运行体曾漂移；本节点要求用门禁收口 | deployment topology gates + gamma-local/prod isomorphism |

## 验收意图

- SIT：端云架构导引与 one-box 拓扑解释必须与部署真相源、metadata、feature-tree 保持一致。
- local_contract：静态门禁验证 feature-tree、拓扑、Strangler 不变量、module mapping、entrypoint 实际承载。
- api_integration：gamma-local 启动后验证 seed-box 关键业务路由与 product-ops 独立入口均可达。
- user_acceptance：交集闭环主路径按后续 CDE UAT 承接，本节点仅声明路径与证据索引。
