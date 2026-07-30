# L2 Business Capability：主页认领、维护与下线 (`homepage-claim-maintain-and-offline`)

> 所属领域：[`shared-homepage-network`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“homepage-claim-maintain-and-offline-journey”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-009`](../../spec.md#scn-009)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`claimed-homepage-basic-maintenance`](./claimed-homepage-basic-maintenance/spec.md)：仅允许认领方维护基础资料，并明确处理越权写入和版本冲突。
- [`homepage-candidate-intake-and-publish`](./homepage-candidate-intake-and-publish/spec.md)：治理方建档候选并在审核后发布。
- [`homepage-claim-request-and-review`](./homepage-claim-request-and-review/spec.md)：定义“认领是共享主页可信治理的关键入口”的可观察主路径、失败语义及父能力交接。
- [`homepage-offline-report-and-history-retention`](./homepage-offline-report-and-history-retention/spec.md)：用户上报状态异常，治理审核后软下线主页并保留历史内容。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 homepage claim maintain and offline journey 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“候选主页发布、认领维护、现实状态异常上报和软下线保留”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 已认领主页可维护基础信息但不能改写用户评价

- 已认领主页可维护基础信息但不能改写用户评价
- 候选主页在审核通过前不能作为正式主页对普通浏览用户公开展示。
- 认领后只能维护基础信息、封面、状态和官方说明，不能直接改写用户口碑。
- 下线统一采用软下线，保留 URL、记录内容、记录口碑和相关群组关系。
- 普通用户可补充主页、纠错和上报下线，但不能直接发布正式主页或修改主页基础信息。
- 审核未通过的认领申请必须返回明确原因或可重提状态。
- baseline 不保留硬删除主页的旧口径，应统一切到软下线。
- 若认领链路或下线合同上线后出现严重治理风险，可先隐藏认领入口或下线上报入口，但不得破坏已下线主页记录保留。
- `Homepage` 写聚合只保存主页权威状态；关注状态、关注数、评分、内容/问答/群组预览、关系边与助手上下文只存在于独立 named read model。
- 详情查询返回 `HomepageDetailView`，当前 viewer 的关注事实由独立 `HomepageViewerFollowSlice` 组合；`HomepageShellView` 只引用已有 typed read model，不以内联 `object` 复制投影形状。

## 6. 契约与依赖

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 homepage claim maintain and offline journey 能力 SIT

- GIVEN 执行“homepage claim maintain and offline journey 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“homepage claim maintain and offline journey 能力”对应动作。
- THEN 直属 Story 共同交付“候选主页发布、认领维护、现实状态异常上报和软下线保留”，失败终态可区分且不产生伪成功事实。
- THEN `Homepage` 聚合不包含 `role: projection` 字段，详情与壳层查询只组合 typed named read model，viewer-scoped 关注状态不进入聚合快照或版本 CAS。

## 8. 开放事项
