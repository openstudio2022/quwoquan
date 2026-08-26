# L2 Business Capability：系统拓扑与组网 (`system-topology-and-networking`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-003](../design.md#dec-003)

## 1. 能力目标

让四环境的南北向公开入口与东西向服务组网只有一套可导航的叙事与唯一 YAML 真相源，agent 与开发者沿特性树即可定位任何组网事实，不再从运维文档与环境目录中拼凑。

## 2. 范围与非目标

### In Scope

- 南北向组网：公开入口 URL role、gateway 数据流、公网 DNS 收敛、TLS profile、CDN 与上传通道。
- 东西向组网：`edge / media / service / data` 子网四平面、本地端口块模型、服务间 URL 分类。
- `prod-hosted` 按平面隔离访问的组网叙事（凭据与账号事实由 `quwoquan_ops/environments/prod/access-isolation.yaml` 拥有）。

### Out of Scope

- 打包、capsule、candidate、activation 与 dev-session：归 [`environment-topology-and-packaging`](../runtime-config/environment-topology-and-packaging/spec.md)。
- 部署管线与灰度回滚：归 [`deliver-deploy-prod-pipeline`](../deliver-deploy-prod-pipeline/spec.md)。
- 各服务进程自治的端口、探针等字面值：归各服务 `config/schema.yaml` 与 `deploy/base/`。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；所有经公开入口访问四环境的 Journey 都消费本能力的组网结果。
  - 本能力处理：声明并收敛南北向公开入口与东西向平面组网的唯一事实。
  - 本能力输出：topology resolver 可投影的组网事实与明确失败终态（漂移、覆盖缺口一律 `GATE_BLOCK` 或 fail closed）。

## 4. Story

- 本能力当前不下设 Story：组网事实由本层能力要求直接叙述，环境级组网收敛的验收与装配由 [`environment-topology-and-packaging`](../runtime-config/environment-topology-and-packaging/spec.md) 的 Story 承接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 南北向公开入口与公网收敛单轨

- 每个环境的 Web、API、RTC、Ops、CDN 与 Upload 公开入口只由 `environments/<env>/runtime.yaml → stackctl target resolver → launch/artifact manifest` 这一唯一数据流生成，每级绑定上游摘要。本规格只引用 URL role（`publicWeb / api / rtc / ops / cdn / upload`）与 resolver，不复制 host、端口或 URL 字面值，任何第二份拓扑复制均为 `GATE_BLOCK`。
- 浏览器 API 固定走同源 `/api` 反代，禁止按请求头猜测 Web/API。媒体读取按 `/media/avatar|image|video` 分段挂在媒体读取 role 下，App 安装包下载固定为 CDN role 的 `/download` 路径，上传保持独立 upload role。
- `quwoquan_ops/environments/domain_governance.yaml` 登记 public、derived deep-link、OAuth callback、east-west、third-party 与 test-only URL 分类，只拥有 URL role 的身份、分类、owner、exposure 与 consumer；各环境 `runtime.yaml` 只拥有 `scheme / host / portRole / pathBase / tlsProfile`。resolver 只合并互不重叠的字段，任何重复 ownership 必须 `GATE_BLOCK`，运行时消费者只能读取 topology resolver 投影。
- `domain_governance.yaml` 的 `dnsZones` 是公网 DNS 记录的唯一声明面，每个 canonical 环境 target 恰好一个 zone。记录名要么是 zone 自己的 apex 与 wildcard 加 `apexFollowers`，要么由该 target 的 topology host 派生；zone 覆盖的名字集合内不得存在第二份人工维护的记录，未被 zone 覆盖的 topology host 必须 `GATE_BLOCK`。
- 收敛的所有权边界按记录类型判定：地址类型（`A`/`AAAA`/`CNAME`）与 zone 级授权类型（`CAA`/`MX`）由计划完全拥有，同组内多余值即漂移、必须清除。`TXT` 是共享类型，计划只拥有自己声明的 `v=` 方法（SPF、DMARC），备案与第三方站点校验令牌既不被占用改写也不被删除，只在 receipt 的 `observedUnmanaged` 中如实上报。
- 记录身份必须在期望侧与现网侧归一：结构化值与线上文本算出同一身份，已一致的记录报 `unchanged` 且不产生 provider 写入；收敛对稳态必须幂等。
- 权威 DNS 写入只经供应商中立 provider 接口进行，服务商由 `dnsProvider.kind` 单点选择。凭据形状是服务商知识，只能由 provider 实现解释，中立层只声明「变量名 -> 部件名」投影；工具链、门禁、CI secret 名与 workflow 不得出现厂商专有字段、API 域名或变量名。DoH 证据必须来自至少两个相互独立的公共解析器，且任一解析器都不得属于权威服务商。
- provisioning 与 ACME challenge 使用两个独立凭据；`acmeChallengeAuthority.providerEnforcement` 必须如实声明 challenge 凭据可写范围由服务商 IAM 强制还是仅由凭据隔离加工具链行为保证，禁止把无法强制的范围描述成已强制。
- 生产 edge 地址是部署时事实，只能经受保护变量注入，禁止入库；它与受版本控制的 SSH 管理端点是两个互不替代的投影，同值也不得合并。未注入时生产地址记录保持缺席并在 plan/apply/verify 的 `pending` 中显式报告，缺席不得降级为占位值，非全球可路由或格式非法的地址必须 fail closed。
- 覆盖或删除现存生产 DNS 记录是破坏性动作：收敛必须先整体算出将发生的动作，未取得显式确认时 fail closed 且不做部分收敛，定时触发只做 plan 与漂移核对；首次下发生产记录不属于破坏性动作。
- canonical publicWeb 始终是 apex，`www` 只能作为 `apexFollowers` 与 apex 共享同一份地址记录，不得用 CNAME 表达；apex 地址缺席时 follower 一同缺席。非生产四个 zone 的公网记录统一解析到 loopback 并发布 null MX 与 SPF deny，生产 apex 不发布 null MX。本域名不收件，CAA 与 DMARC 都不得声明回报邮箱。
- 每个 zone 必须显式选一个 `caaProfiles` 条目：签发公共证书的 zone 用允许清单，不签发的用 `deny-all`；省略 CAA 从而继承 apex 允许清单必须 `GATE_BLOCK`，`caaProfiles` 的选择必须与该 target 的 TLS profile 归属一致。
- 每个 zone 的 apex 必须同时发布 SPF deny 与 `_dmarc` 的 `p=reject` 策略，覆盖 envelope 与 header From 两条伪造路径；任何 mail guard 缺少 `dmarc` 或 DMARC 策略非 reject 必须 fail closed。
- derived link 的 origin 只来自 `publicWeb` role，path 只来自 `quwoquan_service/contracts/metadata/_shared/link_templates.yaml`；App/Data/Service 禁止再拼接第二份公开业务路径。
- Alpha/Beta/Gamma 本地 target 使用同一个 `local-managed` TLS profile，stackctl 从 topology 解析 SAN 并负责证书生成与受管模拟器信任安装；App、测试和脚本不得关闭证书校验、改写 canonical URL 或增加 localhost fallback。`prod-sim` 与 `prod-hosted` 都使用 DNS-01 公共 CA 且由仓内 `tlsProfiles` 拥有签发自动化，`verify` 的证书覆盖面从 `tlsProfiles` 派生，禁止另立 target 清单。
- 非生产 Web hosting 必须以响应头声明 `noindex` 且保持环境访问控制；四环境分别拥有 DNS、证书与配置 composition，不从 Prod 继承。

<a id="req-002"></a>
### REQ-002 东西向平面、端口与访问隔离

- 受支持环境必须在各自 `runtime.yaml` 声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`；四环境网络平面同构，环境差异不得改变平面结构。环境间允许差异化的完整维度清单由 [`environment-topology-and-packaging` REQ-002](../runtime-config/environment-topology-and-packaging/spec.md#req-002) 拥有，本能力不复制。
- 本地 host 端口必须来自 1000 端口块 + plane + 10 端口槽位模型，canonical 端口以 `0` 结尾；端口块与槽位字面值只由 `quwoquan_ops/environments/local_env_port_manifest.yaml` 拥有。
- 服务间（east-west）URL 只经 `domain_governance.yaml` 的 east-west 分类声明，消费者读取 topology resolver 投影，不得自造服务发现面。
- `prod-hosted` 的运维访问按 `edge / media / service / data` 四平面隔离，平面、账号与凭据投影事实只由 `quwoquan_ops/environments/prod/access-isolation.yaml` 拥有；子网 CIDR 仍由 `prod/runtime.yaml` 的 `subnets` 声明，两份文件不得互相复制。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：[`environment-topology-and-packaging`](../runtime-config/environment-topology-and-packaging/spec.md) 的打包与装配、[`deliver-deploy-prod-pipeline`](../deliver-deploy-prod-pipeline/spec.md) 的部署管线，以及所有消费公开入口的业务领域。
- 读取事实：`quwoquan_ops/environments/domain_governance.yaml`、各环境 `runtime.yaml`、`quwoquan_ops/environments/local_env_port_manifest.yaml`、`quwoquan_ops/environments/prod/access-isolation.yaml`。
- 一致性要求：正文只叙事，host、端口、CIDR、账号等字面值只存在于上述 YAML；环境级组网收敛的可观察验收由 [`environment-topology-and-packaging` GWT-001](../runtime-config/environment-topology-and-packaging/spec.md#gwt-001) 承接，本能力不复制其子句。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 南北向组网单轨收敛

- GIVEN `domain_governance.yaml` 与各环境 `runtime.yaml` 的组网声明有效且所有权不重叠。
- WHEN 生成公开入口投影并收敛公网 DNS、TLS 与邮件防护记录。
- THEN 公开入口只经唯一数据流生成，`dnsZones` 覆盖全部 topology host，记录身份归一且稳态幂等。
- AND 破坏性动作 fail closed，DoH 证据来自独立于权威服务商的双解析器，证书覆盖面从 `tlsProfiles` 派生。

<a id="sit-002"></a>
### SIT-002 东西向平面与端口模型成立

- GIVEN 四环境 `runtime.yaml` 与 `local_env_port_manifest.yaml` 的平面与端口声明。
- WHEN 解析任一环境的子网、端口与服务间 URL。
- THEN 四平面完整、端口命中块与槽位模型、east-west URL 只来自治理分类投影。
- AND `prod-hosted` 运维访问按四平面隔离且凭据事实只来自 `access-isolation.yaml`。

## 8. 开放事项

<a id="open-002"></a>
### OPEN-002 SIT-002 部分折叠分句缺直接测试

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：尚缺直接断言 t1「四平面完整」「east-west URL 只来自治理分类投影」与 t2「`prod-hosted` 运维访问按四平面隔离」三个折叠分句的测试——`sit-002.t1` 现绑定的端口块槽位测试只实证端口模型分句，`sit-002.t2` 现绑定的 soak 测试只实证凭据事实来自 `access-isolation.yaml`，其余分句只能靠环境门禁间接兜底。
- 完成判定：`SIT-002` 的上述三个分句各有名实相符的直接测试 `spec_ref`（读 `runtime.yaml` subnets 断言四平面、读 `domain_governance.yaml` east-west 分类断言 URL 投影来源、读 `access-isolation.yaml` 断言 `prod-hosted` 四平面访问隔离），且不再依赖本 OPEN 代替证据。
