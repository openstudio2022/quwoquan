# L3 Story：线下行动与发现底栏入口 (`offline-actions-discovery-tab`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为想把线上心动变成线下同行的用户，
我希望底栏第二格是「行动」（线下行动与发现）目的地，聚合我的交集撮合、我的行动与发起行动入口，
从而不需要在内容流里翻找，就能从「看见」走到「一起去」。

## 2. 范围与非目标

### In Scope

- 底栏第二格由「视频书」替换为「行动」（`MainTabDestination.actions`，壳内存态 embedded 页），
  Web 宽屏主导航同步提供「行动」主入口。
- 视频书不在底栏，其首页信息架构和供给语义由 discovery-content 的 premium-stream 规格拥有；本 Story 不声明视频书在搜索工具栏、壳目的地或分类 Tab 中的位置。
- 「行动」页首版只组合既有对象级读面：交集收件箱卡（recommendation）、「我的行动」入口
  （circle.gathering ByHost/mine）、兴趣配对导流（`/interest-match`）与发起行动 CTA
  （`/gatherings/create`）；不建立第二套业务查询或聚合 Repository。
- 游客可浏览页面与兴趣配对；「我的交集 / 我的行动 / 发起行动」等账号态动作才触发登录，
  关闭回本页安全态（本页无登录门，不会二次弹出），成功进入目标路由
  （`/profile/gatherings` 或 `/gatherings/create`）。

### Out of Scope

- 全局公开 Gathering 发现 feed（需要新的云端公开发现读面，见 OPEN-001）。
- Gathering 生命周期、参与名单与会话绑定（由兄弟 L3 负责）。
- 视频书 premium_stream 供给与环境 readiness（归 `runtime` 环境拓扑规格）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 底栏 IA：行动一级入口

- 底栏五格为 首页 / 行动 / + / 联系 / 我；「行动」渲染 `GatheringActionsDiscoveryPage`，其页面契约为 `circle.gathering_actions_discovery`，surface 为 `homeActionsDiscovery`。
- 视频书不在底栏；其首页位置、沉浸流与退出语义只引用 discovery-content 的当前规格，本 Story 不复制。
- 移动壳与 Web 宽屏壳的 IA 一致：Web 主导航含「行动」入口，
  工作区渲染同一页面。

<a id="req-002"></a>
### REQ-002 诚实降级与登录续接

- 游客态不渲染账号态数据卡（不得以空数据伪装真实读面），以「登录后查看我的交集与行动」
  诚实入口替代；登录成功直达 `/profile/gatherings`。
- 交集收件箱与「我的行动」卡的空态/失败态语义沿用各自对象读面的既有契约，本页不新增
  第二套降级文案。

## 4. 契约引用

- canonical Gathering operation：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`
- canonical Gathering surface：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/ui_config.yaml`
- 父能力公开契约：[`gathering-coordination`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 底栏行动入口

- GIVEN 游客或登录用户位于首页；
- WHEN 点击底栏「行动」；
- THEN 进入线下行动与发现页，底栏保持可见，游客不弹登录门；
- AND 行动入口不占用或重写 discovery-content 拥有的首页分类信息架构。

<a id="gwt-002"></a>
### GWT-002 全局公开行动发现

- GIVEN 用户以游客或登录态进入「行动」页，公开发现读面可返回 canonical Gathering 公开投影；
- WHEN 页面加载全局公开行动发现流，或用户在读取失败后点击唯一重试动作；
- THEN 有结果时呈现可进入公开详情的行动卡，无结果时呈现明确的合法空态，且两者均不触发登录门；
- AND 读取失败时显示可理解错误与唯一重试动作，不以空列表冒充成功；重试成功后留在本页并恢复行动列表。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的公开详情、参与边界与可见性策略。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 全局公开行动发现 feed

- 类型：`future_plan`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：Gathering 读面只有 detail / BySource / ByHost / mine，首版「行动」页只能以入口组合承载；用户尚不能在此浏览全局公开行动，读取失败与合法空态也没有该读面的独立终态。
- 完成判定：`GWT-002` 由对象级 `local_contract`、真实公开发现查询 `api_integration` 与 production Remote composition `user_acceptance` 直接覆盖。
- 依赖：Circle owner 的 canonical 公开发现 operation、App 对象级 typed query 与 Gathering 可见性策略。
