# L3 Story：线下行动与发现底栏入口 (`offline-actions-discovery-tab`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为想把线上心动变成线下同行的用户，
我希望底栏第二格是线下行动与发现目的地「行动」，聚合我的交集撮合、我的行动与发起行动入口，
从而不需要在内容流里翻找，就能从「看见」走到「一起去」。

## 2. 范围与非目标

### In Scope

- 底栏第二格由「视频书」替换为「行动」。`MainTabDestination.actions` 承载壳内存态页面，Web 宽屏主导航同步提供「行动」主入口。
- 视频书保留为 `MainTabDestination.featured` 壳内存态目的地，由首页搜索条右侧固定入口 `home-featured-entry` 激活；视频书页本体、沉浸流与供给语义不变。
- 「行动」页当前只组合既有对象级读面：Recommendation 交集收件箱卡、Circle Gathering ByHost/mine「我的行动」入口、`/interest-match` 兴趣配对导流与 `/gatherings/create` 发起行动 CTA；不建立第二套业务查询或聚合 Repository。
- 游客可浏览页面与兴趣配对；「我的交集 / 我的行动 / 发起行动」等账号态动作才触发登录。关闭登录回本页安全态且不再弹出登录门，成功登录进入对应目标。

### Out of Scope

- 全局公开 Gathering 发现 feed；该能力需要新的云端公开发现读面，缺口由本节点开放事项裁定。
- Gathering 生命周期、参与名单与会话绑定，由兄弟 L3 负责。
- 视频书 premium_stream 供给与环境 readiness，归 `runtime` 环境拓扑规格。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 底栏 IA：行动一级入口、视频书首页顶部入口

- 底栏五格为 首页 / 行动 / + / 联系 / 我；「行动」渲染 canonical 线下行动与发现页面。
- 视频书不在底栏；首页顶部搜索条右侧的固定入口激活 featured 壳目的地，
  沉浸流行为与退出回首页语义不变。
- 移动壳与 Web 宽屏壳的 IA 一致：Web 主导航含「行动」入口，工作区渲染同一页面。

<a id="req-002"></a>
### REQ-002 诚实降级与登录续接

- 游客态不渲染账号态数据卡，不得以空数据伪装真实读面；以「登录后查看我的交集与行动」诚实入口替代，登录成功直达我的行动。
- 交集收件箱与「我的行动」卡的空态/失败态语义沿用各自对象读面的既有契约，本页不新增
  第二套降级文案。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 底栏行动入口

- GIVEN 游客或登录用户位于首页。
- WHEN 点击底栏「行动」。
- THEN 进入线下行动与发现页，底栏保持可见，游客不弹登录门。
- AND 首页顶部「视频书」入口可达并进入沉浸流。

<a id="gwt-002"></a>
### GWT-002 全局公开行动发现流

- GIVEN 存在对当前 viewer 可披露、可公开发现的 Gathering。
- WHEN 用户打开「行动」目的地并加载或翻页公开发现流。
- THEN 页面只渲染 Circle owner 返回的 canonical Gathering 公开投影，且不得以本地入口组合、空账号卡或第二套 Repository 冒充发现结果。
- AND 合法空结果、依赖不可用与 viewer 无权查看必须进入彼此可区分的终态。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的 Gathering owner、公开投影与准入边界。
- 下游结果：移动壳与 Web 宽屏壳消费同一「行动」页面，视频书继续由首页固定入口进入。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 全局公开行动发现 feed

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 Circle owner 的全局公开 Gathering 发现 operation、App typed port、分页页面接入与三层测试；当前 detail / BySource / ByHost / mine 读面和入口组合不得冒充公开发现结果。
- 完成判定：`GWT-002` 的公开投影、分页与三类终态由 local_contract、api_integration、user_acceptance 直接绑定并全部通过。
- 依赖：Circle owner 的公开发现投影、viewer disclosure 与稳定分页契约。
