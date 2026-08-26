# L1 Domain Service：platform-ops-governance（运维横切） (`platform-ops-governance`)

> 一句话定位：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。

## 1. 目标与用户价值

建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。

## 2. 领域边界

### 本领域拥有

- 拥有平台配置发布、可靠性策略、观测告警、运维审计与生产准出证据的生命周期和治理决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- 当前 AppRoot Scenario 不直接经过本领域；本领域只提供被业务领域调用的横切能力。

## 4. 业务能力

- [`commercial-readiness-risk-closure`](./commercial-readiness-risk-closure/spec.md)：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- [`config-and-reliability-governance`](./config-and-reliability-governance/spec.md)：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- [`observability-and-alerting`](./observability-and-alerting/spec.md)：建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
- [`security-privacy-audit`](./security-privacy-audit/spec.md)：统一发布前与运营期的权限、隐私、审计和供应链检查

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 platform ops governance 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力

- 建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。
- 作为统一 Web 门户 `ops-portal` 中 `Platform Ops` 工作域的特性树承载层。
- 所有服务必须接入统一治理策略，不允许按服务自定义核心口径。
- 语义 token、错误码、追踪头、治理参数必须标准化。
- 运维高风险变更必须具备灰度与回滚。
- 面向 `platform-ops` 的管理接口必须从统一控制面元数据生成，禁止手写临时 admin API。
- 三类面必须保持契约与部署拓扑解耦；第一方服务拥有独立 workload 定义，跨服务装配不得引入组合业务 `seed-box`。
- 契约设计不得依赖当前部署拓扑，避免后续拆 Pod 返工。
- 可观测统一且可检索
- Alpha、Beta、Gamma 的 mutable `test_live` runtime 必须由 `stackctl` 同轨完成启动与退出。
- Alpha、Beta、Gamma 的 Research identity 必须在 runtime materialization 时从 `target + canonical acceptance subject` 生成 target-scoped、仓外、`0600`、create-once binding；User 启动只消费其精确 `accountId` allowlist，后续 OTP/login 必须使用同一 subject 并回读同一 account。缺 producer、空 allowlist、旧 session/数据库反查、硬编码 ID 或 binding 漂移一律在启动前 fail closed。
- `dev-session` 只拥有 mutable runtime 生命周期，不创建或保留 UAT 业务数据。Alpha、Beta、Gamma 的受保护 UAT 必须由 `stackctl verify` 从选中 CaseResult 的强类型请求图创建独立 Actor 与交易事实，经目标 canonical HTTPS 和所属领域公开 operation 完成 provision、业务正文、readback 与 cleanup；候选、Provider、target 或请求依赖漂移必须在首个 mutation 前阻断。
- mutable runtime 的内容证据绑定必须使用 receipt-bound `dev-session bind-content` 单轨，显式输入 current running `startupAttemptId`、release/verify/manifest/readiness digest；该动作只验证 exact runtime identity、create-once binding 与 launcher handoff，禁止 materialize、build、refresh 或启动 Compose。同值 replay 幂等，attempt、runtime、readiness 或已绑定值漂移必须 typed `GATE_BLOCK`。
- mutable runtime 退出只能消费当前 target 的 canonical running receipt，并验证零 consumer lease、receipt 与 runRoot runtime plan 一致、Compose project/config/container labels 未漂移。
- mutable runtime 退出不得删除 named volume，也不得从当前源码重渲染旧 runtime；只有 Compose 资源释放、volume 保留和 canonical port 收敛均被回读后，receipt 才能进入 `stopped`。
- 任一 mutable runtime 身份或收敛检查失败必须返回 typed `GATE_BLOCK`，不得写入成功事实。
- immutable runtime 退出必须绑定 canonical running startup receipt 与其 `candidateDigest` 对应的只读 candidate root；candidate 自身 package/Graph/provider/observability/Compose 字节仍须完整校验，但不得因当前工作区已生成下一版 Graph 而拒绝停止旧 candidate。
- 私有仓无法启用原生 required reviewers 时，生产审批事实由本领域独立 hosted approval authority 拥有。受控 GitHub App/webhook 只接收官方 event/action 闭集，验证签名与 delivery ID 后按 request→approved 追加，并绑定 installation、repository、workflow run、head SHA、candidate、environment 与 reviewer decision。
- workflow 只按 candidate/run 读取 hosted exact-byte approval readback；该 readback 必须声明 `nativeProtection=false` 与 `enforcement=external_hosted_ledger`。缺 request/approved、签名无效、重复 delivery 不同 payload、顺序或身份漂移均 `GATE_BLOCK`，不得用 job queue、Deployment status 或人工布尔值替代。
- 门禁 GATE_BLOCK 结构化输出只经 `quwoquan_ops/cli/lib/gate_output.py` 统一 schema 落盘 `.qwq_output/env/repo/runs/gate/`。`quwoquan_ops/gate/gate_repo.sh` 经 EXIT trap 调 `emit_gate_repo_summary.py` 发射整链结构化 summary，按 scope 独立落盘（以上支撑 DOM-001 的机器可读裁定能力）。
- `spec_ref` 测试证据只认单行绑定形态：ref 所在行、ref 之前有大小写不敏感的 `spec_ref` 记号（注释或常量声明）。裸字符串字面量（fixture、断言消息、Go `SpecRef:` 数据字段）不构成绑定，负例由 feature-tree 合约测试锁定。
- 评审派发 `quwoquan_ops/cli/review_dispatch.py`（工程归属经 `make feature-context` 机器裁定归本领域）输出的 plan.json 把 gate 拆为可直跑 `gates` 与 `parameterized_gates` 两字段。占位符是唯一判据：需实参的 gate 行必须在 checklist 内自带 `<...>` 占位符，不维护平行的已知目标闭集。参数化门由执行方绑定实参后执行或显式判 N/A，不得无参直跑。

<a id="req-003"></a>
### REQ-003 候选绑定的保留数据修复必须在业务 API 启动前完成

- 已激活 immutable release 的历史事件负载阻断服务健康时，只允许经 `stackctl repair` 的显式确认动作恢复；不得直接写业务数据库、复活旧候选、绕过健康门或重新激活 Data release。
- 修复必须绑定当前 immutable candidate、stopped runtime、零 consumer lease、既有 active release import/creator receipt 与 canonical attestation；任一身份或字节漂移必须在写入前 `GATE_BLOCK`。
- 修复拓扑只允许启动候选内的 owning store 与 candidate-packaged importer；业务 API、relay 与 consumer 必须保持停止，release/creator 输入只读挂载，named volume 不得 purge。
- 每次动作必须记录 candidate/release/receipt、受管命令、修复事件摘要与 teardown readback；首次修复与期望零修复的幂等复核分别生成稳定 receipt。
- runtime health 与 `stackctl health` 必须保留确定排序的失败 check、完整失败详情摘要与 body digest，不得只保存 middleware 泛化后的错误。

<a id="req-004"></a>
### REQ-004 环境可用性判据必须覆盖依赖就绪、必需容器现况与容量水位

- `stackctl health` 的服务探针必须按各服务真实探针形态判定：声明独立就绪端点的服务必须同时探存活与就绪，两者作为可分别定位的 check 上报；只声明单一深探针的服务不得被补一个恒真的浅探针充数。
- 就绪失败必须与存活失败可区分，并向上传导为 `stackctl health` 与 `up` 的失败；任何环境不得因存活探针返回成功而判定为可用。
- startup receipt 的 `running` 只表达启动时刻的事实，不表达当前可用。消费 receipt 判定环境可用时必须复验该 target 必需容器的当前状态与健康：任一必需容器已退出或 unhealthy 必须返回 typed blocker，并落到 `runtimeHealthStatus` 的降级态。
- App 编译安装前的 preflight 必须消费上述复验结果，依赖未就绪时在安装前阻断，不得以 ui-only 或 test-live 的告警档放行。
- 本地容器运行时的容量水位必须成为 `doctor`、`up`、`package`、`dev-session` 与 App preflight 的前置判定：宿主可用空间与容器存储可用空间任一低于声明阈值必须 `GATE_BLOCK`，报告给出实测可用量、阈值、可回收量与精确回收命令。
- 容量耗尽必须表达为 typed blocker，不得只依赖对底层 `no space left on device` 文本的字符串匹配。
- 容量不足或候选身份漂移不得阻断本领域白名单恢复动作本身；恢复路径必须在环境已经不可用时仍然可执行。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 platform ops governance 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 可观察结果：mutable `test_live` teardown 绑定同一 running receipt、runRoot 与 Compose project，零 lease 时仅删除该 project 的容器/网络并保留 named volume，成功后回读端口释放与 `stopped` receipt。
- 可观察结果：`stackctl verify` 只加载选中 CaseResult 的 Provider 依赖闭包，在同一 TestDataSession 内执行 provision、Patrol/业务正文、readback 与 cleanup，并生成 run-bound、non-promotable 的追加式 receipt；Patrol 只消费控制面注入的 typed Actor handoff，不接收 fixture、裸 token 或调用方注入 ID。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。
- 禁止结果：不得用当前工作树重新推断旧 runtime、手工删除容器、purge volume，或在资源未收敛时伪造 `stopped` receipt。
- 可观察结果：immutable teardown 在当前 workspace 前进后仍从 receipt candidate 自身恢复精确 Provider/observability/image composition，受控释放旧 Compose 容器与网络并保留 named volumes。
- 可观察结果：GitHub webhook request/approved 事件经签名验证后进入独立 append-only approval authority，同一 delivery 幂等、不同 payload 冲突，workflow exact-byte 回读同一 candidate 且明确不冒充原生 protection。

<a id="dom-002"></a>
### DOM-002 active release 保留数据修复与启动前证据

- 条件：当前 immutable candidate 尚未运行、consumer lease 为零，且其 release binding 与既有 active import receipt 精确一致。
- 可观察结果：显式确认的修复只启动 owning store 与 candidate-packaged importer；首次修复精确收敛已知 legacy 负载，随后期望零修复的重放零写且字节幂等，两次均输出可读回的稳定 receipt。
- 可观察结果：修复后业务 API 才可启动；若启动或健康仍失败，受管报告包含精确失败 check、完整详情摘要和 body digest。
- 禁止结果：candidate/release/receipt/期望数量/CAS/cleanup 任一漂移不得写成功事实；不得启动 API/relay/consumer、删除 named volume、推进 release 或绕过 owning importer 直写数据库。

<a id="dom-003"></a>
### DOM-003 依赖就绪、必需容器现况与容量水位的可用性证据

- 条件：某 local target 已有 running startup receipt，其必需容器集合与容量阈值均由该 target 的 canonical 声明派生。
- 可观察结果：服务探针矩阵对声明独立就绪端点的服务同时产出存活与就绪两个 check；就绪失败时 `stackctl health` 失败，且失败 check 可定位到具体服务与被探端点。
- 可观察结果：必需容器已退出或 unhealthy 时，环境可用性判定返回 typed blocker 与降级 `runtimeHealthStatus`，App preflight 在编译安装前阻断。
- 可观察结果：宿主或容器存储可用空间低于阈值时，`doctor`、`up`、`package`、`dev-session` 与 App preflight 在执行前 `GATE_BLOCK`，报告含实测可用量、阈值、可回收量与回收命令。
- 可观察结果：容量耗尽以 typed blocker 表达，同一判定在容量恢复后不再阻断。
- 禁止结果：不得因存活探针成功、receipt 仍为 `running` 或容量检查缺席而判定环境可用。
- 禁止结果：不得把容量耗尽降级为无类型错误或纯字符串匹配，也不得让容量不足阻断白名单恢复动作本身。

## 7. 工程归属

- App：`quwoquan_ops`
- CI：`.github/workflows`
- Contracts：`quwoquan_service/control-plane/platform-ops/contracts`
- Service：`quwoquan_service/control-plane/platform-ops`
- 测试：
  - `local_contract`：`quwoquan_ops/tests`
  - `api_integration`：`quwoquan_service/control-plane/platform-ops`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 platform ops governance 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 全局容量规划与灾备观测统稿 L2

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺全局容量规划、灾备与观测统稿的 L2 owner，相关知识散落。具体 P0 缺口已在 [`commercial-readiness-risk-closure/spec.md#OPEN-007`](./commercial-readiness-risk-closure/spec.md#open-007)（备份恢复演练与 RPO/RTO）与 [`commercial-readiness-risk-closure/spec.md#OPEN-008`](./commercial-readiness-risk-closure/spec.md#open-008)（日志统一 collector 上云）登记，本 OPEN 只补「统稿 L2 结构」缺口，不重复登记具体风险项。
- 完成判定：`DOM-003` 的容量水位可用性证据获得统稿 owner——本 L1 下建立容量/灾备/观测统稿 L2（经 prd→design 流程），上述两条现存 OPEN 由该 L2 承接或保留原节点并被其引用；`make verify-feature-tree` 退出 0。

