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
- seed manifest 与环境数据隔离。

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

- tagRef、canonicalEntityId、entityRef、relationEdge 有明确发布物或 fixture 来源。
- alpha/beta/gamma/prod 数据策略不漂移。
- 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

<a id="req-002"></a>
### REQ-002 标签真相源为数据工程 control_plane/governance/taxonomy；publish/tags 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy

- 标签真相源为数据工程 `control_plane/governance/taxonomy`；`publish/tags` 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy。
- 实体归一产物必须能映射到运行时 `canonicalEntityId`。
- seed manifest 必须区分 alpha、beta、gamma、prod 数据策略。
- 新增数据发布物必须提供可执行 schema 校验或 canonical contract fixture，且失败时不得进入发布包。
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
- THEN tagRef、canonicalEntityId、entityRef、relationEdge 有明确发布物或 fixture 来源。
- THEN alpha/beta/gamma/prod 数据策略不漂移。
- THEN 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 数据工程同源输入验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：tagRef、canonicalEntityId、entityRef、relationEdge 有明确发布物或 fixture 来源。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
