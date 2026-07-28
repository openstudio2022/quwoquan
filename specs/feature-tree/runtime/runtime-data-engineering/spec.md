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
- 新增数据发布物必须提供可执行 schema 校验或 canonical contract fixture，且失败时不得进入发布包。
- 第一方 App 可见业务数据禁止由 T3/UAT、API 脚本、数据库脚本或环境 bootstrap 创建；基础设施灰度探针不得进入业务 query/projection。
- 单元/合约测试只写 tempfile 临时根，pytest 不得向仓内根或 `QWQ_OUTPUT_ROOT` 落盘（conftest 落盘隔离门）。

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
- THEN 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 数据工程同源输入验收

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前尚缺同一 release 对 tag、creator/avatar、entity homepage、article/image/video 与 public media slice 的完整闭包及四环境 activation/rollback/readback receipt；环境 fixture 和直接 seed 仍可形成伪业务数据。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 覆盖 release/import/API/media/App readback。
