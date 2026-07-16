# Runtime 端云扩展目录（D0/F1 当前规范）

> 本文件只提供实施入口，不定义第二套架构。业务对象边界、应用接口与门禁以
> `specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md`
> 和同目录 `acceptance.yaml` 为准；metadata 结构与编译合同以
> `quwoquan_service/contracts/metadata/DESIGN.md` 为准。

## 1. 不变量

1. 每个业务对象只有两层业务接口：
   - **Object Application Facade**：按 command/query facet 暴露用例。
   - **Object Data Ports**：对象专属 `AggregateStore`、业务命名 Reader 与 typed Slice。
2. command 绑定聚合 owner；加载聚合、执行领域行为，并以 expected version、
   idempotency key 和同库 outbox 完成提交。
3. query 绑定 named Reader/Slice，直接读取投影或查询存储，禁止为了查询加载聚合。
4. `ContractGraph` 在构建期由唯一 compiler 生成；服务启动只注入 generated
   operation descriptor，不读取或扫描 metadata 文件。
5. MongoDB、PostgreSQL、Redis、ES、对象存储和外部服务实现只放在各服务
   `internal/infrastructure/**`；composition root 显式选择并注入具体 adapter。
6. 禁止跨对象泛型 CRUD、动态 Filter/Map、按存储类型运行时选厂和反射式字段拦截链。
7. beta、gamma、prod 必须使用真实 adapter；prod 禁止装配 Memory、Noop、Mock、
   fixture、seed 或默认 secret。

## 2. 唯一实施顺序

```text
Spec Entry / acceptance
  -> metadata
  -> commercial validate
  -> ContractGraph + codegen
  -> Object Application Facade
  -> Object Data Ports
  -> service infrastructure adapters
  -> local_contract
  -> api_integration
  -> user_acceptance（涉及用户旅程时）
  -> alpha / beta / gamma / prod 准出
```

标准命令：

```bash
# 1. metadata 修改后，先做 commercial 语义校验
cd quwoquan_service
go run ./tools/qwq_contract validate \
  --metadata-dir contracts/metadata \
  --profile commercial

# 2. 再生成并检查唯一 ContractGraph 及派生产物
make codegen
make codegen-app
make verify-contract-graph-commercial

# 3. 回到仓库根执行分层验证与总门禁
cd ..
make gate
```

任何一步失败都必须停止；不得通过 alias、fallback、双读、双写、allowlist 或降低测试
断言继续推进。

## 3. 目标目录

```text
quwoquan_service/services/{service-name}/
├── cmd/{entry}/main.go
│   └── 显式 composition root：config -> platform clients -> adapters
│       -> object facades -> generated transport
├── internal/
│   ├── domain/{object}/
│   │   ├── model/                 # aggregate、owned entity、value object
│   │   └── ports/                 # 对象专属 AggregateStore 等领域端口
│   ├── application/{object}/
│   │   ├── *_command_facade.go    # command facet
│   │   ├── *_query_facade.go      # query facet
│   │   ├── *_reader.go            # 业务命名 Reader port
│   │   └── *_slice.go             # typed query Slice
│   ├── adapters/
│   │   ├── http/                  # generated operation -> Facade
│   │   └── mq/                    # typed event -> application use case
│   └── infrastructure/
│       ├── persistence/           # 对象 Store/Reader 的 Mongo/PG 实现
│       ├── projection/            # projector、checkpoint、rebuild
│       ├── cache/                 # Reader 的可选缓存实现
│       └── external/              # 外域或第三方 adapter
├── tests/
│   ├── local_contract/
│   └── api_integration/
└── configs/
```

约束：

- `domain` 和 `application` 不导入数据库、缓存或网络驱动。
- transport adapter 只依赖 application facet，不依赖 infrastructure。
- infrastructure 实现对象端口；`main.go` 显式装配，不按 metadata 在运行期决定实现。
- 单一根 `quwoquan_service/go.mod`；服务目录不得创建独立 Go module。
- generated 文件只由 codegen 产生，禁止手改。

## 4. 对象边界判定

新增子实体前必须先判定 `owned_entity` 还是 `separate_aggregate`，不得先选表或集合再倒推
领域边界。

### 4.1 `owned_entity`

同时满足以下条件才可归入聚合：

- 生命周期完全依附 owner，不能独立创建、删除、授权或保留。
- 所有写入都由同一 aggregate owner 执行，并需要同一事务维护不变量。
- 集合有明确、可验证的 cardinality bound。
- 不需要独立并发版本、幂等键、审核流程、隐私删除周期或外部写 owner。

### 4.2 `separate_aggregate`

满足任一条件即应独立：

- 独立生命周期、状态机、权限、保留期或审计要求。
- 独立高并发写入、版本冲突或幂等边界。
- 被多个聚合或服务直接引用、写入或订阅。
- 成员数量无上界，或会随时间持续增长。
- 需要独立 outbox、重放、迁移、归档或删除。

**无界集合禁止内嵌聚合。** 列表、消息、评论、成员关系、互动、回执、审核记录等持续增长
对象必须独立建模，并通过 ID、事件或 Slice 与 owner 关联。

## 5. 扩展场景

### EX01：新增业务对象

1. 在 feature-tree 冻结 owner、生命周期、权限、SLO、回滚和验收。
2. 按第 4 节判定 aggregate、owned entity、value object、projection、
   append-only fact、runtime session 或 external reference。
3. 新建或更新对象 metadata，声明 actor、operation、store role、事件、错误和测试合同。
4. commercial validate 后 codegen。
5. 手写对象 Facade/Data Ports 与真实 adapter，补三层测试。

### EX02：新增或调整聚合成员

- 必须记录 cardinality bound 与 owner invariant。
- 从有界变为无界时，直接拆为独立聚合并执行一次性数据迁移；不保留双模型。
- owned entity 不得拥有独立写入口；需要独立写入口即重新判定边界。

### EX03：新增 command

- metadata 声明 operation、actor、command facet/method、aggregate owner、错误与事件。
- command facade 负责 authz、幂等、加载、领域行为、commit + outbox。
- Store 端口必须表达 expected version；adapter 在同库事务内提交状态与 outbox。
- api integration 必须覆盖成功、版本冲突、重复请求、权限和持久化失败。

### EX04：新增 query 或 Slice

- metadata 声明 query facet/method、named Reader、typed Slice、分页与可见性。
- Reader 名称表达业务目的，例如 detail、author page、inbox，而不是通用查询能力。
- query facade 不加载 aggregate，不接受动态 Filter/Map。
- local contract 校验 Slice/codegen；api integration 使用真实查询或投影存储验证分页、
  顺序、权限和空态。

### EX05：新增事件或投影

- `events.yaml` 声明 typed payload、producer、consumer、ordering 与隐私策略。
- command 的 authoritative adapter 同事务写 outbox。
- consumer 使用 inbox/checkpoint 保证幂等；投影必须支持 replay/rebuild 和 DLQ。
- 投影 Reader 只读 projection store，不回写 aggregate。

### EX06：新增或替换存储 adapter

- 对象端口保持业务语义，具体 adapter 放在目标服务 infrastructure。
- metadata 声明 authoritative/projection/cache/external role、索引、TTL 与迁移。
- composition root 显式替换实现；不得按存储类型在运行期动态选厂。
- authoritative adapter 必须通过 version/idempotency/commit+outbox conformance。
- 存储迁移必须一次性切换；不保留长期双写或自动 fallback。

### EX07：新增 API operation

- `service.yaml` 先声明 method、path template、operation id、actor、application facet、
  request/response 与 errors。
- generated transport 只做解析、OperationContext、Facade 调用和 RuntimeErrorResponse 映射。
- URL、operation、surface、route 不得在 handler、App 或文档维护第二份常量。

### EX08：新增字段、错误、隐私或行为合同

- 字段进入 `fields.yaml`；错误进入 `errors.yaml`；隐私、行为与 UI 合同进入对应 metadata。
- commercial validate 后统一 codegen，禁止手改 Go/Dart/OpenAPI 产物。
- 错误链覆盖 RuntimeFailure、RecoveryPolicy、HTTP、App mapper、用户恢复与观测。

### EX09：新增 App 消费

- App 只通过 generated DTO/operation 与域 Repository Provider 访问远端。
- alpha fixture、beta/gamma Remote 与 prod package purity 必须同源验证。
- 新页面同步完成 route/surface、页面质量矩阵、行为归因和 user acceptance。

### EX10：新增服务或部署单元

- 先确认 domain owner 与现有服务边界；源码服务和部署 workload 不互相冒充。
- 使用 `make new-service SERVICE=<name>-service PORT=<port>` 创建骨架。
- 同批更新 process/domain/plane/module/workload topology 真相源。
- composition root 逐对象显式装配 Facade 与 adapter；公共 runtime 只提供跨域机制。

### EX11：新增测试与环境准出

- `local_contract`：metadata、边界、Facade、端口、生成物、Mock/fixture 行为。
- `api_integration`：真实 HTTP、真实存储、outbox/inbox、投影、错误和跨服务合同。
- `user_acceptance`：用户旅程、页面状态、弱网、权限、SLO、灰度和回滚。
- acceptance 中声明的测试文件必须真实存在；未执行的环境证据不得标记 implemented。

## 6. 四环境合同

- **alpha**：允许显式 test adapter 与 contract fixture，仅用于 local contract；不得伪装集成证据。
- **beta**：Remote/API + 真实 adapter + beta seed，验证人工验收和错误恢复。
- **gamma**：与 prod 同构的真实 adapter、事件与投影，执行 api integration 和
  user acceptance。
- **prod**：只装配真实依赖，缺配置或依赖必须 fail-fast；禁止 Memory、Noop、Mock、
  fixture、seed、测试端点和默认 secret。

## 7. 出口检查

```text
□ AppRoot Journey/Scenario 与 L1/L2/L3 归属明确
□ acceptance 已映射 SIT/GWT/contract 与三层测试
□ object kind、owner、cardinality、actor、lifecycle 已冻结
□ command/query 分流正确；query 未加载 aggregate
□ commercial validate、codegen、check 幂等通过
□ Facade/Data Ports 对象专属，composition root 显式
□ adapter 位于服务 infrastructure，生产装配无测试替身
□ local_contract / api_integration / user_acceptance 证据完整
□ alpha/beta/gamma/prod 数据源、SLO、灰度、回滚与观测闭环
□ make gate 通过，且无旧兼容、第二真相源或放宽项
```
