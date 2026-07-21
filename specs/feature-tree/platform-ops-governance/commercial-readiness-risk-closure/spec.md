# L2 特性：commercial-readiness-risk-closure

## 目标

把运维运营平台的商用准入从“功能存在”提升为“风险归零后才可发布”。本 Story
不接受“已知风险上线”“后续补”“人工记住补偿”等完成口径：

- 仓库内可修复的断点必须在本 Story 内实现、测试并关闭；
- 外部账号权益、真实法务主体信息、IdP 凭据或 prod-hosted 凭据缺失时，必须
  `GATE_BLOCK`，不能把它降级为已接受风险；
- 发布准入要求 `docs/outstanding_risks_backlog.md` 中本 Story 负责的
  `R-OPS-*` 全部已解决，或被外部前置条件机器阻断且没有任何发布逃逸路径。

## 用户价值

- 运维人员看到的配置、日志、指标、告警、灰度状态和运营数据都来自真实系统；
- 高风险控制面动作只能由两个不同、已验证的 operator 对同一 payload 审批并留下
  原子 receipt；
- 任意一次生产发布都能证明“构建一次、同一 digest、真实 SLO 回读、串行放量、
  可回滚、可恢复”；
- 发生日志链路、数据面、主机、页面体验或关键业务异常时，能够检索、告警和处置，
  不依赖假数据或静默 fallback。

## 范围

### In Scope

1. **身份与危险动作**
   - Portal OIDC Authorization Code + PKCE；
   - 服务端 JWKS/MFA/scope 校验；
   - 菜单按 scope 过滤；
   - actor 只从已验证 principal 派生；
   - 双签 payload digest、职责分离、幂等与原子 mutation/audit/outbox receipt。
2. **遥测与日志可靠性**
   - startup body digest 幂等；
   - Behavior gzip、clientEventId、occurredAt、事务 outbox；
   - RuntimeLogger 优先队列、TTL、指数退避、DLQ、422 解队头；
   - 服务日志可靠 spool、actorHash/文本查询、ANR/卡顿 rollup 与告警。
3. **发布与供应链**
   - GitHub Actions 全部固定 40 位 commit SHA；
   - CODEOWNERS、最小权限、环境保护验证；
   - Build Once、OCI digest、SBOM、签名/provenance、same-digest gate；
   - rollout 全局锁、CAS release ledger、真实 Prometheus readback、自动回滚 receipt；
   - prod 冷启动配置/证书/Secret/SPA 探针。
4. **可观测、灾备与容量**
   - Prometheus/Alertmanager/OTel/exporter 生产 composition；
   - PostgreSQL/Mongo/SLS 备份与恢复演练；
   - RPO/RTO、容量和成本水位；
   - 触发 → 通知 → ack → resolved 的值班闭环。
5. **配置、灰度维度与真实数据**
   - IaC 配置快照与全部 governed workload ACK；
   - appVersion/userId/province/carrier 四维灰度路由；
   - province/carrier 必须来自可信服务端/边缘解析，不信任客户端自报；
   - Portal 页面不得以 seed、hardcode 或合成趋势冒充生产数据。
6. **验收诚信**
   - acceptance 中 planned/recorded 路径必须真实存在；
   - `local_contract`、`api_integration`、`user_acceptance` 与 stackctl 证据可复跑；
   - content-service 与全部触达服务可完整编译。

### Out of Scope

- 购买 GitHub/IdP/云厂商套餐或填写企业法务主体信息；这些是外部前置条件，缺失即
  阻断发布，仓库不得伪造；
- 未经人工确认执行 prod-hosted 放量、回滚或破坏性恢复；
- 为绕过外部前置条件新增自建弱鉴权、假证书、假法务信息或本地成功回执；
- 把 `prod-gray` 建成第二环境，或维护第二套 topology/config/metric 真相源。

## 统一设计决策

### D1 风险状态不是发布参数

发布流程不接受 `accept_risk`、`warn_only`、`skip` 或兼容模式。本 Story 负责的风险
只有两种机器状态：

- `resolved`：实现、三层测试和触发范围 gate 均通过；
- `blocked_external`：外部前置条件缺失，所有 release/deploy 入口 fail-closed。

`blocked_external` 不是完成，也不能进入生产。

### D2 控制面写入采用原子 receipt

仍保留在线写入口的高风险 product control-plane 动作，最终执行必须由一个对象专属
事务完成：

```text
approval decisions (2 principals + same digest)
  -> execution intent / idempotency receipt
  -> object/workflow state
  -> audit event
  -> transactional outbox
```

外部 side effect 由 outbox worker 幂等执行；HTTP handler 不再“先写状态、再发事件、
最后尽力写审计”。

平台发布、放量和回滚不开放 Portal mutation API。Portal 只读 CI/CD/stackctl 发布账本；
唯一执行面是受保护 GitHub Environment + `stackctl deploy`，其职责分离、全局锁、CAS
和回滚 receipt 在 RP3/RP4 收口。禁止把 platform-ops 容器内调用仓库脚本重新包装成
“双签控制面”。

### D3 日志采用本地耐久 spool

服务 stdout 仍是主机采集兜底；HTTP exporter 使用 bounded append-only spool，
按 severity 优先、指数退避和 TTL 投递。永久 4xx 进入 DLQ 并继续后续记录，临时
网络/5xx 不丢 WARN/ERROR。

### D4 灰度地理与运营商由可信边缘派生

App 只上送 appVersion 和已认证 userId。province/carrier 由可信边缘根据受控 IP
数据库或可信上游头解析并覆盖客户端值；未知即不参与匹配。客户端不新增平台判断，
业务层不直接读取 SIM/运营商 SDK。

### D5 Build Once 与发布串行化

CI 产出不可变 ReleaseManifest：

```text
git commit -> OCI digest -> SBOM digest -> provenance/signature
           -> config digest -> portal digest -> test evidence digests
```

gray-initial/carry-on/full 只引用该 manifest；全局发布锁和 CAS release ledger 阻止
并发放量，回滚只能选择 manifest 中已验证的上一 digest。

### D6 生产证据不可被本地证据替代

local/gamma 可证明契约和实现；以下结论只能由 prod-hosted/外部系统证明：

- IdP/JWKS/MFA 与真实 operator scope；
- GitHub 受保护分支/环境；
- 真实域名证书和法务主体；
- 生产 exporter、告警通知、备份恢复、灰度流量和回滚。

缺证据时保持 `GATE_BLOCK`。

## 任务包

| 包 | 任务 | 关闭风险 |
|---|---|---|
| RP1 | startup/Behavior/RuntimeLogger/服务日志 spool 与 ANR rollup | R-OPS-STARTUP-IDEMPOTENCY、R-OPS-RUNTIMELOG-DELIVERY、R-OPS-BEHAVIOR-CONSISTENCY、R-OPS-LOG-COLLECTOR |
| RP2 | OIDC/RBAC、principal actor、双签原子 receipt/outbox | R-OPS-PORTAL-AUTH、R-OPS-DUAL-SIGN |
| RP3 | Actions SHA、CODEOWNERS、最小权限、ReleaseManifest/SBOM/provenance | R-OPS-GH-PROTECTION、R-OPS-BUILD-DEPLOY-DIGEST |
| RP4 | rollout lock/CAS、Prometheus readback、冷启动与执行面单轨 | R-OPS-SLO-READBACK、R-OPS-GRAY-ROLLBACK-EXEC、R-OPS-PROD-COLDSTART、R-OPS-BACKEND-CONTRADICTION |
| RP5 | 观测栈、灾备恢复、容量成本、真实数据对账 | R-OPS-OBS-STACK、R-OPS-DR-CAPACITY、R-OPS-DATA-SOURCE |
| RP6 | Config ACK 全覆盖、发布包 canonical config-root、可信 province/carrier、acceptance 路径诚信 | R-OPS-CONFIG-PLANE-PROD、R-OPS-ACCEPTANCE-PHANTOM |
| RP7 | 全仓编译、三层测试、stackctl release 验证、backlog 关闭 | 全部 |

## 完成定义

- 所有 RP 的 contract/local_contract/api_integration 绿；
- Portal `npm test`/`npm run build` 与 App 定向 analyzer/test 绿；
- `make verify-metadata`、single-track、观测规则、拓扑、供应链与 acceptance gate 绿；
- `stackctl verify --env prod --kind all --profile release` 绿；
- prod-hosted 受保护操作由用户明确批准后，输出真实 deploy/health/inspect/doctor、
  告警闭环和恢复演练证据；
- 本 Story 负责的 backlog 项全部勾选并写入日期、证据；否则状态保持未完成。
