# Data Plane Binding Runbook

本 Runbook 解释 `environment-runtime` 中 `dataPlane` 的建模、验证和变更流程。它不替代环境源文件、备份计划、容量计划或 metrics manifest，也不增加 `stackctl` 命令。任何未知字段、未声明物理坐标或无法 read back 的变更都 fail closed。

## 合同边界与字段闭集

`dataPlane` 只允许 `resources` 与 `bindings` 两个字段，二者都必须是非空 mapping。键和字段都是闭集；未知字段应视为拼写错误或尚未评审的合同扩展，不能透传。

资源键是稳定的逻辑引用。每个 `resources.<resource>` 必须且只能包含：

- `engine`：`postgres`、`mongodb`、`elasticsearch`、`redis` 或 `object_storage`。
- `physicalIdentity`：安全字符串，或只含 `external`、`local`、`prevalidate` 的 mode mapping。字符串在三个 mode 中都代表同一 identity；mapping 按 mode 选择 identity。
- `failureDomain`：非 endpoint 的安全故障域标识。
- `shared`：布尔值；任何共址资源必须为 `true`。

每个 `bindings.<service>.<slot>` 必须且只能包含：

- `service`、`slot`：必须和 binding key 精确拼成 `<service>.<slot>`。
- `engine`、`resource`：engine 必须和被引用资源一致。
- `namespace`：逻辑 database/index/bucket 范围。
- `secretRef`：环境变量引用名或 `null`，不得放 secret 值或 endpoint。
- `shared`、`required`：布尔值。
- `backupRef`、`metricsRef`：非空的备份与监控所有权引用。
- `inject`：环境投影描述符 mapping。

`inject` 的 descriptor 必须有 `kind`。kind 闭集为 `dsn`、`uri`、`addr`、`endpoint`、`database`、`index`、`api_key`、`literal`。通用字段只有 `kind`、`secretRef`；仅 `literal`、`database`、`index` 可声明 `value`。`literal.value` 只能为字符串 `true`/`false` 且禁止 `secretRef`；`database`/`index` 显式声明 `value` 时也禁止 `secretRef`。其他 kind 禁止 `value`。

`service: deployment-control` 是 deployment-only 的唯一分类条件，与 slot 名称无关：它的 `inject` 必须严格为 `{}`。其他 service 的 `required: true` binding 必须有非空 `inject`。Search 与 telemetry 的管理员入口仍是精确槽位 `deployment-control.search.objects.admin` 和 `deployment-control.telemetry.admin`；不能用其他 deployment-control slot 替代。

## 逻辑与物理是正交轴

不要从逻辑 owner 推导物理部署，也不要从物理共址推导逻辑所有权：

- 物理轴：`resources`、`physicalIdentity`、`failureDomain` 和 resource-level `shared` 描述进程、集群或托管实例在哪里，以及哪些 resource alias 实际共址。
- 逻辑轴：binding 的 `service`、`slot`、`namespace`、凭据、`backupRef` 和 logical metrics profile 描述谁读写哪组数据。
- 同一 physical identity 可以承载多个隔离 namespace；不同 physical identity 也可以由同一 service/slot 迁移前后承载。两种关系都必须显式声明，不能靠名字猜测。

Search 对象必须恰有一个 reader、至少一个 writer 和一个精确 admin，三类绑定共享 resource、namespace 与 `vN` generation，但凭据按 reader/writer/admin 分离。Telemetry 与 runtime-logs 的 namespace、备份和逻辑 metrics owner 必须分离；其管理员使用精确 telemetry admin slot。

## 共址示例

以下片段展示 search 与 telemetry 在 `local`/`prevalidate` 共用一个 Elasticsearch、在 `external` 拆开的声明。共址涉及的两个 resource 和所有引用它们的 binding 都必须 `shared: true`。

```yaml
dataPlane:
  resources:
    search-elasticsearch:
      engine: elasticsearch
      physicalIdentity:
        external: prod-search-elasticsearch
        local: elasticsearch
        prevalidate: elasticsearch
      failureDomain: workstation-alpha
      shared: true
    telemetry-elasticsearch:
      engine: elasticsearch
      physicalIdentity:
        external: prod-telemetry-elasticsearch
        local: elasticsearch
        prevalidate: elasticsearch
      failureDomain: workstation-alpha
      shared: true
  bindings:
    deployment-control.search.objects.admin:
      service: deployment-control
      slot: search.objects.admin
      engine: elasticsearch
      resource: search-elasticsearch
      namespace: quwoquan_objects-v1
      secretRef: null
      shared: true
      required: true
      backupRef: search-objects
      metricsRef: search-elasticsearch-physical-metrics
      inject: {}
    deployment-control.telemetry.admin:
      service: deployment-control
      slot: telemetry.admin
      engine: elasticsearch
      resource: telemetry-elasticsearch
      namespace: product-ops-observability
      secretRef: null
      shared: true
      required: true
      backupRef: product-observability-admin
      metricsRef: telemetry-elasticsearch-physical-metrics
      inject: {}
```

校验器会分别展开 `external`、`local`、`prevalidate` 分组。同一 mode 下 identity 相同即视为共址；字符串 `physicalIdentity` 会进入全部三个 mode 的分组。任何共址组中，只要一个 resource 或其任一 binding 没有 `shared: true`，验证都会失败。

## 拆分示例

以下片段展示两个互不共址、各自只有一个 binding 的资源。identity 必须在每个 mode 都不同；单 binding 资源可显式声明 `shared: false`。

```yaml
dataPlane:
  resources:
    content-mongodb:
      engine: mongodb
      physicalIdentity:
        external: prod-content-mongodb
        local: content-mongodb
        prevalidate: content-mongodb
      failureDomain: data-a
      shared: false
    chat-mongodb:
      engine: mongodb
      physicalIdentity:
        external: prod-chat-mongodb
        local: chat-mongodb
        prevalidate: chat-mongodb
      failureDomain: data-b
      shared: false
  bindings:
    content-service.mongodb:
      service: content-service
      slot: mongodb
      engine: mongodb
      resource: content-mongodb
      namespace: quwoquan_content
      secretRef: PROD_CONTENT_MONGO_URI
      shared: false
      required: true
      backupRef: content-mongodb
      metricsRef: content-mongodb-metrics
      inject:
        CONTENT_MONGO_URI:
          kind: uri
    chat-service.mongodb:
      service: chat-service
      slot: mongodb
      engine: mongodb
      resource: chat-mongodb
      namespace: quwoquan_chat
      secretRef: PROD_CHAT_MONGO_URI
      shared: false
      required: true
      backupRef: chat-mongodb
      metricsRef: chat-mongodb-metrics
      inject:
        CHAT_MONGO_URI:
          kind: uri
```

这是合同形状示例；新增的 backup/metrics 引用必须先在各自正式 manifest 中存在，不能直接复制占位名字到环境源文件。

## Namespace、role、backup 与 capacity

- **Namespace**：每个 binding 拥有独立 database/index/bucket 范围。除 Search reader/writer/admin 的同一原子 generation 外，不同 binding 不得复用同一 `resource/namespace`；共址不授予共享 namespace。
- **Role/credential**：`secretRef` 和 `inject.*.secretRef` 只保存凭据引用身份。Prod Search reader/writer/admin、telemetry 与 runtime-logs 必须按 owner/role 分离，部署管理员只由 `service: deployment-control` 派生且不注入长驻 workload。变更后必须以最小权限 ACL readback 证明允许和拒绝面。
- **Backup**：`backupRef` 属于 binding 的逻辑数据集。Prod 引用必须解析到 `environments/prod/backup-recovery.yaml` 中一个 dataset；其 `resourceRef` 等于 binding resource，并覆盖 `namespace` 及 `inject` 中所有显式 database/index value。共用物理集群不表示可以共用逻辑备份：telemetry 与 runtime-logs 必须使用不同 `backupRef`。
- **Capacity**：容量预算和 noisy-neighbor 判定按 `binding + namespace` 记录；physical resource 聚合只用于诊断。当前 `dataPlane` 字段闭集没有 `capacityRef`，不得私加字段或把容量写进 identity。变更审批必须引用现行受管容量证据；无法证明 source/target 的连接数、存储、水位、复制 lag 与回滚余量时停止。

`metricsRef` 可以指向两类 profile：

- `logical_namespace`：归逻辑 owner 所有，必须声明 owner label 与 namespace patterns，并使用区别于物理 exporter 的 owner-scoped scrape job。
- `physical_resource`：归物理资源所有，`ownerLabel` 必须为 `null`、`namespacePatterns` 必须为 `[]`，scrape job 必须等于 physical profile 的 job。

每个 `physicalProfileRef` 全局只能有一个 `scope: physical_resource` binding profile。Search admin 使用 `search-elasticsearch-physical-metrics`；search reader/writer 使用 `search-objects-metrics`。Telemetry admin 使用 `telemetry-elasticsearch-physical-metrics`；telemetry 和 runtime-logs 使用各自 logical profile。

## 绑定变更与 CAS

任何变更先从当前不可变 artifact 读取 `bindingDigest`，形成：

```yaml
fromBindingDigest: sha256:<current>
toBindingDigest: sha256:<candidate>
```

`fromBindingDigest` 是 compare-and-swap 前置条件：执行 cutover 前必须 read back 当前生效 digest，并与它精确相等；不相等表示期间已有其他变更，必须停止、重新 package 并重新评审，禁止覆盖。`toBindingDigest` 必须来自候选 package，禁止人工计算或手填替代候选 artifact。相同二元组重放必须是幂等 no-op；任一 digest、namespace/role、backup、metrics 或容量证据漂移都阻断。当前没有通用的 data-plane cutover `stackctl` 命令；上述二元组是迁移审批与执行器必须遵守的协议，不应虚构命令绕过它。

审批必须声明绝对 `rollbackDeadline`（或等价的开始时间 + 正回滚预算）。窗口从 quiesce 开始，到 source 恢复写入且旧 digest/readback 再次通过为止；不得在失败后重开相对计时。任一步预计越过窗口，或 source 在目标接收新写后已无法证明一致，就保持写栅栏并升级人工裁决，不能盲切旧 binding。

## 迁移与回滚顺序

对 namespace、资源或 physical identity 的迁移严格按以下顺序：

1. **备份**：验证 source backupRef 覆盖全部逻辑成员，并取得可恢复证据。
2. **复制**：向 target resource 做全量复制，保持 source 为当前 authority。
3. **追平**：应用增量，测量 lag/watermark；未追平不得进入 quiesce。
4. **Quiesce**：暂停或栅栏写入，记录最终 source watermark。
5. **Cutover**：在 `fromBindingDigest` CAS 成功后激活 `toBindingDigest`；CAS 失败立即停止。
6. **Readiness/readback**：验证目标健康、权限、namespace 完整性、watermark 和生效 binding digest；仅进程存活不算成功。
7. **Rollback**：若 readiness/readback 失败，在仍可证明 source 一致性时回切旧 binding，恢复写入并验证旧 digest/readback。若 target 已接收不可逆新写入，先处理数据回放/冲突，不得盲目切回。

整个过程不得删除 source 备份或提前释放旧资源。Backup、复制和 readback receipt 必须脱敏，不能包含 secret 或完整 endpoint。

## 门禁清单与现有 stackctl 入口

依次检查，任一项缺失或漂移都 `GATE_BLOCK`：

1. `dataPlane`、resource、binding 和 inject descriptor 均满足字段闭集，required ContractGraph resource 唯一绑定。
2. `physicalIdentity` 在 `external/local/prevalidate` **逐 mode** 比较；每个冲突 mode 的全部 resource/binding 都显式 `shared: true`。
3. Namespace 无越权碰撞；Search generation 原子一致；role/credential 分离且 endpoint 引用一致。
4. `backupRef` 覆盖全部逻辑成员并有可恢复证据；`metricsRef` owner/scope 正确且 required coverage 为 100%。
5. Binding/namespace 容量、连接、水位、lag 与 noisy-neighbor 证据在预算内。
6. Candidate 已封存 `toBindingDigest`，生效 readback 等于 `fromBindingDigest`，CAS 尚未失效，回滚 deadline 仍可满足。
7. Cutover 后 readiness、ACL、watermark、数据完整性与 binding digest readback 全部通过；失败时在原窗口内恢复旧 digest 并再次 read back。

只使用仓库已经存在的入口（命令前缀均为 `python3 quwoquan_ops/cli/stackctl.py`）：

- `package --env <environment> --target <target> --kind runtime`：生成不可变 runtime candidate，并封装 canonical data-plane binding 与 digest。
- `verify --env <environment> --target <target> --kind topology --profile smoke`：验证拓扑合同；需要更大验证面时使用现有 `--kind all`，不要假设它执行数据迁移。
- `health --target <target> --scope full`：在候选已启动或 hosted runtime 可达后收集完整健康证据。Health 不替代 binding digest readback、数据完整性或备份恢复证明。

参数和值应按目标环境填写并由正常审批路径提供。以上命令没有 backup、copy、catch-up、quiesce 或 cutover 子命令；这些步骤必须由已有的资源专用受控流程完成，不能把 Runbook 文字当成尚不存在的自动化。

## Research 身份边界

四环境当前 `productLifecycleState` 为 `research`，研究内容访问由环境级 `researchContentIsolation` 及其受管身份/证明链约束。`physicalIdentity` 只标识数据库、缓存、搜索或对象存储的物理实例，不是 research actor、用户、账号、persona、session 或凭据。不得把上述身份、白名单成员、PII、token、endpoint 或 secret 编入 resource identity、namespace 或 digest 输入。

Research tester 不得用 anonymous guest、手工 Bearer、共享管理员凭据或 data-plane `secretRef` 冒充研究身份。Alpha/Beta/Gamma 的 release 消费核验必须经 canonical 入口签发短 TTL 凭据：

```bash
python3 quwoquan_ops/cli/stackctl.py --output-format json \
  research-consumer-credential \
  --env <alpha|beta|gamma> \
  --release-id <immutable-release-id> \
  --verify-run-id <current-verify-run-id>
```

Bearer session 与 attestation 只从 stdout 交给当前 tester 进程并留在内存；`report.json` 只能记录脱敏 hash/过期时间，禁止落盘、进入 binding、digest、日志或回执。Prod 不在此研究凭据命令的环境闭集内。

Research 身份验证和 data-plane binding 验证是两条独立证据链：前者证明谁能访问研究内容，后者证明服务绑定到哪个数据资源。两者都通过才可形成环境 readiness，任一通过都不能替代另一项。

## DP4 状态

DP4 不在本次实现范围内。`dataRelease` 仍为 **OPEN / typed blocker**：当前 local import 继续从 port role 拼接 MongoDB/PostgreSQL/Redis 物理坐标，hosted import 继续直接读取 `mongoUriEnv`、`redisAddrEnv`、`userPostgresDsnEnv`、`mediaRootEnv`；这些路径尚未消费 canonical data-plane binding/digest。字段保持不变；在 [`deliver-deploy-prod-pipeline OPEN-009`](../../specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#open-009) 按 `SIT-002` 验收关闭前，不得声称 data release 已由本 Runbook 或 data-plane binding 自动化覆盖。
