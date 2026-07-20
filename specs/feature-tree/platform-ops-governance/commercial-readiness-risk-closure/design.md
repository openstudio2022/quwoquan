# Design：commercial-readiness-risk-closure

## 设计目标

本设计把身份、危险动作、遥测、供应链、发布、观测、灾备、配置和验收统一成
一个生产准入状态机。目标不是扩大控制面功能，而是删除所有“功能存在但不可证明”
的中间态。

## 总体架构

```text
metadata / feature-tree / policies
  -> codegen + static gates
  -> local_contract
  -> api_integration (real stores)
  -> immutable ReleaseManifest
  -> prod gray-initial
       -> OIDC/scope
       -> global rollout lock + CAS ledger
       -> real Prometheus SLO
       -> alert/ack/recovery
       -> config ACK/drift
       -> backup/restore check
  -> carry-on
  -> full
```

任一箭头失败即停止；不存在 warn-only 或人工补记成功。

## 1. 身份与权限

### Portal

- SPA 使用 Authorization Code + PKCE，不在 localStorage 保存 token；
- 只从 access token claims 读取 roles/permissions；
- generated `portal_menu.yaml` 的 `permission_scope` 同时控制菜单可见性；
- 401 清会话并回登录页，403 保留已认证态并显示结构化禁止原因。

### 服务端

- production 必须配置 `OPS_OIDC_ISSUER/AUDIENCE/JWKS`；
- OIDC verifier 强制 issuer、audience、expiry、RS256、MFA 与低基数 scope；
- middleware 在验签前删除 `X-Actor`、`X-User-Id` 和全部 client identity headers；
- audit actor 只能来自 `PrincipalFromContext`，不存在 header fallback。

### 外部前置

真实 IdP tenant/client/JWKS/MFA policy 不是仓库可伪造资源。缺失时服务 fail-fast，
Portal release build fail-fast，prod release gate fail-closed。

## 2. 原子双签

定义对象专属 `DangerousMutationStore` 事务端口：

```text
CommitApprovedMutation(
  objectType, objectId, intent, payloadDigest, idempotencyKey,
  approvals[2], nextDocument, nextWorkflow, audit, outboxEvents
) -> MutationReceipt
```

约束：

- 两个不同 account principal；
- approver 不能是同一主体的别名或 device actor；
- 两个 approval 必须绑定同一 payload digest；
- intent/payload 变化立即失效旧 approval；
- receipt 以 `(objectType, objectId, intent, payloadDigest, idempotencyKey)` 唯一；
- document/workflow/audit/outbox/receipt 同一 PostgreSQL 事务；
- product control-plane side effect 只由 outbox worker 幂等执行；
- handler 不再忽略 workflow/audit/publish 错误。

该事务端口只服务仍保留在线写入口的 premium-pool takedown。平台发布、放量与回滚
不属于 Portal 在线业务写入：Portal 只读 CI/CD 发布账本，唯一执行面是受保护的
GitHub Environment + `stackctl deploy`。仓库不得为了“共用双签”重新开放容器内脚本
执行或第二套发布 API；发布职责分离、幂等与回滚证据由 RP3/RP4 的环境审批和 CAS
release ledger 保证。

## 3. 可靠遥测与日志

### startup / Behavior

- batch key 始终是 canonical body SHA-256；
- proof 只证明来源，不参与 batch identity；
- gzip 在 transport 边界显式解压并限制解压后大小；
- `clientEventId`、`occurredAt` 必填且具唯一索引；
- 业务事实与 outbox 同事务，失败返回结构化非 2xx。

### App RuntimeLogger

- 单一优先队列：ERROR > WARN > INFO；
- 每条记录携带 createdAt、attempt、nextAttemptAt、expiresAt；
- 临时失败指数退避 + jitter；
- 422/其他永久 4xx 进入 DLQ 并继续后续记录；
- 队列容量保护关键级别，丢弃必须有指标；
- 网络恢复主动 flush。

### 服务日志 spool

- stdout/stderr 始终写主输出；
- HTTP exporter 追加到本地 bounded spool，再异步发送；
- 2xx 删除，409/重复视为成功，429/5xx/网络错误退避，永久 4xx 入 DLQ；
- spool 与 DLQ 位于 runtime output，不写源码树；
- exporter 自身日志不得再次进入 exporter，防反馈环。

## 4. 供应链与 GitHub 治理

- 所有 Actions `uses:` 固定 40 位 commit SHA；
- workflow 顶层 `permissions: contents: read`，逐 job 只增必要权限；
- `.github/CODEOWNERS` 覆盖 workflows、Ops policies、metadata 和 prod manifests；
- CI 生成 ReleaseManifest、CycloneDX/SPDX SBOM 与 SLSA provenance；
- OCI/portal/config artifact 均使用 digest，不允许 `latest`；
- deploy workflow 只下载构建 job 的制品，不得重建。

GitHub 私有仓库套餐若不支持 branch protection/rulesets，机器审计将其标记
`blocked_external` 并阻断 production workflow。升级套餐或转为满足安全要求的托管
方案后才可关闭，不能用仓内脚本宣称等价。

## 5. 发布状态机

### Release ledger

PostgreSQL `release_ledger`：

- `service` 主键；
- `version` CAS；
- current/previous manifest digest；
- current stage；
- lock owner/lease expiry/fencing token；
- last SLO snapshot、approval receipt、rollback receipt。

### 流程

1. 获取全局/服务发布租约；
2. CAS 校验 from manifest/stage；
3. 确认两个 operator approval；
4. 部署 gray-initial；
5. 读取真实 Prometheus（窗口 + 最小样本）；
6. continue / pause / rollback；
7. 写 receipt 并释放租约。

Prometheus、锁、CAS、回滚目标任一不可用时停止。

## 6. 可观测、灾备与容量

- 生产观测栈：Prometheus、Alertmanager、OTel、node/podman/Mongo/Postgres/Redis
  exporter；
- runtime log rollup 把 ANR、jank、delivery/spool/DLQ 转为低基数指标；
- 所有 alert 必须能在 Portal ack 并关联 audit；
- PostgreSQL 使用一致性备份 + WAL/PITR；Mongo 使用 replica/快照；SLS 使用跨
  project/region export；
- restore 永远恢复到隔离目标并执行业务校验，禁止只验证“备份文件存在”；
- RPO/RTO、容量和成本阈值来自 policy，不复制到页面。

## 7. 配置 ACK 与可信灰度维度

- 每个 governed workload 使用共享 config bootstrap helper，启动时必须 resolve +
  report ACK；
- ACK 包含 service/instance/image/config/desired/effective/source/updatedAt；
- Portal drift 的 expected set 从 workload topology 派生，缺 ACK 本身就是 drift；
- appVersion/userId 来自可信请求上下文；
- province/carrier 在边缘从可信代理 IP 信息解析，先删除客户端同名头再重建；
- 解析失败即维度未知，不默认命中。

## 8. 数据与验收诚信

- Portal 每个卡片必须携带 source/freshness/window；
- seed 只允许 alpha/local_contract，beta/gamma/prod 页面不得回退 seed/hardcode；
- acceptance planned/recorded 路径存在且测试可执行；
- feature tree、CR、backlog、generated artifacts 与代码同一变更收口；
- release gate 读取 backlog：本能力负责项存在未关闭即阻断。

## 回滚策略

- 代码回滚：回到上一 ReleaseManifest digest；
- 配置回滚：切换上一 config digest，不在线编辑；
- 日志/遥测变更：canonical schema 单轨，失败时停止升级而不是双写旧协议；
- 数据迁移：新表/索引先 expand，验证后切读写，再删除旧结构；当前未上线阶段不保留
  长期兼容分支。
