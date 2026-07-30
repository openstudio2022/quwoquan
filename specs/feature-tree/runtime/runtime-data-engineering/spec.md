# L2 Business Capability：运行时数据工程 (`runtime-data-engineering`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。

## 2. 范围与非目标

### In Scope

- tagRef 发布物。
- canonical entity 与 entityRef。
- relationEdge 候选事实。
- canonical publish、immutable release、环境 activation receipt 与数据隔离。

### Out of Scope

- 在线推荐排序实现。
- 业务服务在线写路径。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：图片来源、下载字节、授权与发布引用均可回放。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：缺任一 required rights 字段的资产不能进入 release。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：不满足 admission 的候选以 typed issue 阻断。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 数据工程同源输入验收

- tagRef、canonicalEntityId、entityRef、relationEdge、creator/avatar 与 post media 均有 canonical publish/release 来源。
- alpha/beta/gamma/prod 只激活 immutable release，数据策略不漂移且无环境 fixture/self-seed 旁路。
- 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

<a id="req-002"></a>
### REQ-002 标签真相源为数据工程 control_plane/governance/taxonomy；publish/tags 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy

- 标签真相源为数据工程 `control_plane/governance/taxonomy`；`publish/tags` 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy。
- 实体归一产物必须能映射到运行时 `canonicalEntityId`。
- immutable release 保持环境无关，同一 digest 由 alpha、beta、gamma、prod 产生独立 activation/import/rollback receipt。
- content importer receipt 必须携带 `sourceOwner=qwq_data` 与等于 release attestation `payloadSha256` 的 `manifestDigest`，并保留 exact post/author readback binding。
- 每个环境的回滚准出必须写 create-once `environment_release_lifecycle_exit`，同时绑定 original apply/verify、rollback-to rollback/verify、replay apply/verify，并重新证明 replay `manifestDigest` 等于 original immutable payload digest；不得用三份互不关联的 run 目录代替 Exit receipt。
- `release discard` 除进程互斥外还必须保护长期验收引用；passed `release-readiness.json` 是永久保护证据，UAT 则由 Data-owned、append-only `release_acceptance_lease_event` acquire/revoke 显式包围。只有已绑定 acquire 的 revoke 才能关闭 lease，revoke 不得撤销 passed readiness 的保护。
- 同一 environment 同一时刻只允许一份未 revoke acceptance lease；该 lease 必须阻断该 environment 对任意 release 的 apply、rollback、verify 或另一份 lease acquire，环境级进程锁覆盖“检查 active lease → 写事件/执行 ship”的完整临界区，不同 environment 的锁相互独立。
- 新增数据发布物必须提供可执行 schema 校验或 canonical contract fixture，且失败时不得进入发布包。
- 第一方 App 可见业务数据禁止由 T3/UAT、API 脚本、数据库脚本或环境 bootstrap 创建；基础设施灰度探针不得进入业务 query/projection。
- 单元/合约测试只写 tempfile 临时根，pytest 不得向仓内根或 `QWQ_OUTPUT_ROOT` 落盘（conftest 落盘隔离门）。

<a id="req-003"></a>
### REQ-003 标签发布物必须自带采集通道与在线消费方式声明

- taxonomy 每个节点必须声明采集通道与消费方式；采集通道取值限于拍摄元数据、地点选择、创作者勾选、点评勾选、行为事件与仅管线派生。
- 取值为仅管线派生的存量节点进入基线清单并只减不增，新增节点不得使用该取值。
- 消费方式必须至少包含召回过滤、排序因子、交集判定与搜索筛选之一，缺失声明的节点不得进入 canonical publish。
- 同一现实概念跨轴出现时由节点自身声明同义引用，跨轴权重传播只读取该声明，不按路径前缀推测轴间关系。
- 境外行政区必须覆盖声明的最小目的地集合，覆盖不足时视为发布物不完整并阻断发布。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 数据工程同源输入验收

- GIVEN 执行“数据工程同源输入验收”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“数据工程同源输入验收”对应动作。
- THEN tagRef、canonicalEntityId、entityRef、relationEdge、creator/avatar 与 post media 均有 canonical publish/release 来源。
- THEN 同一 release digest 在 alpha/beta/gamma/prod 产生独立 activation/import/API/media/rollback receipt，且无 fixture/self-seed 旁路。
- THEN importer、public feed/media 与 Ops/UAT readiness 均绑定同一 immutable payload digest。
- THEN 每个环境具备 original→rollback→same-digest replay Exit receipt。
- THEN 活跃任务、passed readiness 或未 revoke acceptance lease 任一存在时 cleanup 均 fail-closed。
- THEN release A 的未 revoke acceptance lease 阻断同一环境 release B 的 ship 与 lease acquire，且不同环境可独立推进。
- THEN 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

## 8. 开放事项

<a id="open-002"></a>
### OPEN-002 标签发布物在创作侧没有采集通道，绝大多数标签处于孤儿状态

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前绝大多数标签没有任何用户侧写入通道，内容标签只能由数据侧 release import 产生，创作者发布的内容不携带标签。地理轴节点数量最多，但在地点选择结果被解析为标签引用之前同样不产生真实分布。由此召回过滤、排序因子、交集判定与搜索筛选都只能作用于数据侧内容，标签数量增长不转化为用户可感知的能力，在通道打通前继续扩充只会等比例增加孤儿。
- 完成判定：拍摄元数据、地点选择与创作者勾选三条通道均能把标签写入用户发布的内容。taxonomy 全部节点的采集通道与消费方式声明齐备，且不存在新增的仅管线派生取值。境外最小目的地集合校验通过，标签在召回、排序、交集与搜索中的真实分布可从发布物回读。

<a id="open-003"></a>
### OPEN-003 采集通道已在发布物声明，但排序侧读不到，所有标签同权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前发布物虽已按 REQ-003 为每个节点声明采集通道，但该声明止步于 taxonomy，没有随标签进入在线特征。排序侧对一篇内容的全部标签施加同一个由停留深度与来源渠道推导的权重，因此拍摄元数据测量出的机身与焦段、地点选择解析出的行政区、创作者自行勾选的风格三者在召回与排序中完全等价。自填标签的噪声因此被当作实测证据参与分发，而实测证据也拿不到应有的置信优势。对象标签倒排只存扁平 tagRef 数组，不承载单条赋值的权重与置信度，所以该信息在存储层同样缺位。
- 完成判定：单条标签赋值的采集通道与置信度可从发布物经倒排索引到达排序侧，排序按该置信度区分实测标签与自填标签。置信度只有发布物声明这一个来源，Go 侧不得按 tagRef 路径前缀推测采集通道。倒排索引改造后，反查与子树前缀反查的命中集合与改造前等价，并有真实存储证据。
