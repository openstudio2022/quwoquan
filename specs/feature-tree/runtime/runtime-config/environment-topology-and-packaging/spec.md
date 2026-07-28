# L3 Story：环境拓扑与打包 (`environment-topology-and-packaging`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为打包或部署环境的工程角色，
我希望从每个环境的 `runtime.yaml` 解析完整网络、公开入口与 workload 装配，并生成可复现发布包，
从而确保 alpha、beta、gamma 与 prod 使用同一拓扑规则且差异可审计。

## 2. 范围与非目标

### In Scope

- “环境拓扑与打包”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 环境拓扑与打包

- 受支持环境必须在各自 `runtime.yaml` 声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`。

<a id="req-002"></a>
### REQ-002 各环境 runtime.yaml 声明完整网络与公开入口

- 受支持环境必须在各自 `runtime.yaml` 声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`；`publicBases` 只能由 target resolver 生成。
- `alpha` 与其他环境使用同一 Remote composition/schema/网络平面，只能在容量、endpoint、访问控制、数据 release 和第三方 sandbox 策略上差异化。
- 本地 host 端口必须来自 1000 端口块 + plane + 10 端口槽位模型，canonical 端口以 `0` 结尾。
- App / Service env package 都必须携带 runtime schema 版本、artifact policy 摘要与机器可读报告。
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- 同一环境存在多个部署 target 时，每个 target 必须写入独立 package 目录，并从环境 `urlRoles + target urlOverrides + portProfile` 的解析结果投影 App 运行时端点；禁止复制环境默认 target 的 URL 或跨 target 复用可变产物。
- `prod-hosted` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL；`prod-sim` 仍属于 `prod` 环境，但全部公共入口必须使用 `*.sim.quwoquan.com`，不得命中生产 host、增加第五环境或放宽 `prod-hosted` 纯度门。
- Web Origin 固定为 Alpha `https://alpha.quwoquan.com:17000`、Beta `https://beta.quwoquan.com:18000`、Gamma `https://gamma.quwoquan.com:19000`、Prod `https://quwoquan.com`；浏览器 API 固定走同源 `/api` 反代，禁止按请求头猜测 Web/API。
- API、RTC、Ops、CDN 与 Upload 分别使用 `api|rtc|ops|cdn|upload.<env>.quwoquan.com`；媒体读取按 `/media/avatar|image|video` 分段，App 下载固定为 CDN `/app/download`，上传保持独立 host。
- `quwoquan_ops/environments/domain_governance.yaml` 登记 public、derived deep-link、OAuth callback、east-west、third-party 与 test-only URL 分类；运行时消费者只能读取 topology resolver 投影，不得再定义公开 authority。
- 非生产与 prod-sim 公共入口使用 DNS-01 公共 CA；App、测试和脚本只使用系统信任链，禁止私有根证书注入、`badCertificateCallback`、`curl -k` 或 host 改写。
- 非生产 Web 产物必须 `noindex` 且保持环境访问控制；四环境分别拥有 DNS、证书、配置与发布物，不从 Prod 继承。

<a id="req-003"></a>
### REQ-003 双端本地运行持有可释放 consumer lease

- `quwoquan_app/run.sh -d <device>` 是显式本地运行的 canonical launcher；IDE launch profile 只能薄包装该入口，不得复制环境装配。
- iOS Simulator 的无显式环境 `flutter run` 仅在 Debug 配置下作为兼容薄入口：Xcode phase 先准备 Alpha Remote，再消费 `build_launcher_handoff` 生成的唯一 canonical Alpha handoff；禁止在 Xcode 脚本复制第二套 endpoint、Dart defines、证书信任或 effective manifest。
- Android 从 topology 推导包名、设备与全部 `adb reverse` 端口，在 Flutter 构建前获取 lease，并通过 `trap` 在退出时释放；iOS Simulator 同源准备环境包、设备 CA 与 native runtime manifest。
- 该入口在四环境固定编译 production `lib/main_prod.dart` 连接完整 Remote topology；iOS Debug 兼容入口必须在 Xcode backend 前覆盖 Flutter 默认 target，禁止 alpha runner、fixture override 或只提供 mock/public-plane 子集的本地进程。
- Gradle 只验证 launcher 已提供完整 runtime package 与设备证明；Xcode 除上述 iOS Debug Alpha 兼容 handoff 外同样只验证，不得获取 Android lease、静默推断 Beta/Gamma/Prod、复制配置或吞掉准备脚本失败。
- iOS Profile/Release、显式非 Alpha 环境与 Beta/Gamma/Prod 均必须携带 canonical launcher 的 target、Dart defines digest、runtime config digest 与 immutable effective manifest digest，缺一即在安装前 `GATE_BLOCK`。
- Android 启动前必须完成 gateway、media、公共 CA 与 `adb reverse` 预检。
- iOS Simulator 启动前必须完成 gateway、media、系统公共 CA、Dart defines 与 native manifest 一致性预检；任一预检失败时停止 Flutter 启动。
- 活跃 lease 存在时，`stackctl down`、环境矩阵强制清理和端口强制回收必须 `GATE_BLOCK`。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 环境拓扑与打包

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“环境拓扑与打包”对应的公开行为。
- THEN 各环境 `runtime.yaml` 均声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`。
- AND `stackctl package --env prod --target prod-sim|prod-hosted` 分别生成 target 隔离的 App 包，包内 URL 与 resolver 生成的 `publicBases` 一致，且 `prod-hosted` 仍拒绝本地或测试 host。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Android 与 iOS App 会话保护本地运行时

- GIVEN 开发者通过 canonical launcher，或无显式环境的 iOS Simulator Debug 兼容入口，在指定设备启动 alpha App。
- WHEN Flutter 构建、运行、正常退出或异常退出，或并行环境任务尝试 down/强制清理。
- THEN Android lease 在构建前绑定设备、包名与 topology 端口，App 退出时由 trap 释放；iOS Debug 兼容入口只消费 canonical Alpha handoff 并生成同源 native runtime manifest。
- AND 本地 Alpha 与 Beta/Gamma/Prod 使用同一 production Remote composition；首页、视频、消息和我的主页均由已激活 release 与真实服务 query 提供，启动器和 UAT 不得隐式切入 Mock、fixture 或残缺 public plane。
- AND Android 的 gateway、media、系统公共 CA 或 `adb reverse` 预检失败时 App 不启动；iOS 的完整 runtime package、native manifest、系统公共 CA 或端点预检失败时 App 不启动。
- AND 无显式环境的 iOS Simulator Debug `flutter run` 默认进入 canonical Alpha；其他缺失 canonical handoff 的 direct build 在安装前失败，用户不得看到由开发配置缺失制造的启动恢复页。

## 6. 依赖

- 前置要求：[`runtime-config`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 环境拓扑与打包 验收证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 Alpha launcher/UAT 仍可选择 fixture runner，release UAT 仍偏 Gamma-only；尚缺删除输出后对 alpha、beta、gamma、prod 的 Remote App/Service 全包重建、显式 target activation、拓扑无漂移与跨 target 隔离矩阵。
- 目标：补齐四环境 Remote App/Service package 与 release activation 重建矩阵，并断言 runtime schema、artifact policy、public base、host purity、composition attestation 与机器报告均来自对应环境及 target。
- 完成判定：`GWT-001` 的四环境 App/Service/activation 重建矩阵全部通过且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 公网 DNS 与证书 live 准出

- 类型：`external_dependency`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库已具备 DNS plan/apply/verify、CAA、邮件防护与 DNS-01 证书签发链路，但当前会话未提供非生产/生产公网 IPv4、IPv6、Cloudflare zone token/zone id 与 ACME account email，不能伪造 live DNS/TLS 成功证据。
- 目标：通过受保护变量提供 `QWQ_NONPROD_PUBLIC_IPV4/IPv6`、`QWQ_PROD_PUBLIC_IPV4/IPv6`、`QWQ_DNS_API_TOKEN`、`QWQ_DNS_ZONE_ID`、`QWQ_ACME_ACCOUNT_EMAIL`，执行 apply、证书签发、四 target HTTPS/WSS 验证并保存 receipt。
- 完成判定：DNS A/AAAA/CAA/MX/SPF、反向解析、证书 SAN/有效期及四环境公开角色 HTTP/WSS 探针全部通过，且证据报告可回读。
