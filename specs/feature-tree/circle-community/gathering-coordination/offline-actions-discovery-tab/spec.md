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
- 视频书保留为壳内存态目的地（`MainTabDestination.featured`），由首页顶部固定入口
  （搜索条右侧，`home-featured-entry`）激活；视频书页本体、沉浸流与供给语义不变。
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
### REQ-001 底栏 IA：行动一级入口、视频书首页顶部入口

- 底栏五格为 首页 / 行动 / + / 联系 / 我；「行动」渲染
  `GatheringActionsDiscoveryPage`（页面契约 `circle.gathering_actions_discovery`，
  surface `homeActionsDiscovery`）。
- 视频书不在底栏；首页顶部搜索条右侧的固定入口激活 featured 壳目的地，
  沉浸流行为与退出回首页语义不变。
- 移动壳与 Web 宽屏壳的 IA 一致（R-XP6）：Web 主导航含「行动」入口，
  工作区渲染同一页面。

<a id="req-002"></a>
### REQ-002 诚实降级与登录续接

- 游客态不渲染账号态数据卡（不得以空数据伪装真实读面），以「登录后查看我的交集与行动」
  诚实入口替代；登录成功直达 `/profile/gatherings`。
- 交集收件箱与「我的行动」卡的空态/失败态语义沿用各自对象读面的既有契约，本页不新增
  第二套降级文案。

## 4. 验收

<a id="gwt-001"></a>
### GWT-001 底栏行动入口

- GIVEN 游客或登录用户位于首页；
- WHEN 点击底栏「行动」；
- THEN 进入线下行动与发现页，底栏保持可见，游客不弹登录门；
- AND 首页顶部「视频书」入口可达并进入沉浸流。

测试证据：
- `quwoquan_app/test/local_contract/runtime/shell/main_app_shell_widget__local_contract_test.dart`
  （五栏断言、行动 tab 切换、首页顶部视频书入口）。
- `quwoquan_app/test/local_contract/service/circle_service/circle_management/gathering/gathering_actions_discovery_page__local_contract_test.dart`
  （游客/登录两态、兴趣配对可达、文案唯一入口）。

## 5. OPEN

### OPEN-001 全局公开行动发现 feed

- 现状：Gathering 读面只有 detail / BySource / ByHost / mine，无全局公开发现 feed；
  首版「行动」页以入口组合承载。
- 待办：contracts-first 增加公开发现读面（服务端 operations + App typed port），
  页面接入发现流并补三层测试；完成后删除本 OPEN 并将行为并入 REQ-001。
