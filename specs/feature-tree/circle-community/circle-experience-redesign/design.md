# L2 群组体验重构 — 设计方案

## 设计动因

L2 的任务不再只是“把圈子推荐做得更好”，而是要解决两件更本质的事：

1. 首页和搜索如何在一个 `群组` 入口里同时承接兴趣型圈子与组织型主页。
2. 详情页如何在不分裂内核的前提下，给出 `通用圈子模板` 与 `组织主页模板` 两套自然的前台体验。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-experience-redesign/spec.md` | 已冻结领域对齐、同频发现、双模板详情 |
| `circle-experience-redesign/acceptance.yaml` | `A1~A4` 已可测 |
| `circle-community/design.md` | 已冻结群组总入口、CircleGroup 子单元与统一发布内容模型 |
| `global-search-experience/spec.md` | 已冻结首页和搜索统一用户词为 `群组` |

结论：

- 本 L2 的设计重点从“单一圈子发现”升级为“群组发现 + 双模板详情”。
- 仍需保持 domain taxonomy、推荐、助理上下文的统一真相源。

## 对标输入分析

| 对标 | 吸收点 | 不吸收点 |
|---|---|---|
| 微信 | 单一入口容纳不同关系对象 | 不照搬通讯录与群聊深绑定 |
| Discord Discovery | 分类、推荐、发现混合 | 不照搬频道层级和 server naming |
| 小红书 | 统一入口下多种内容与对象被发现 | 不把所有详情页都变成话题页 |

## 方案对比

### 方案 A：继续只做兴趣型圈子发现

优点：

- 改动最少

缺点：

- 学校、班级、公司、部门仍无法自然接入
- 首页和搜索继续裂成两套心智

### 方案 B：群组发现页里拆成“组织专区”和“圈子专区”两套独立分页

优点：

- 前台语义很清楚

缺点：

- 发现页、搜索页、推荐逻辑都会被拆成两套
- 不利于用户在一个入口中流畅探索

### 方案 C：群组单入口 + 类型徽章 + 双模板详情

优点：

- 首页、搜索、推荐统一
- 详情层按模板差异化
- 与 circle 域和搜索结果面最容易保持一致

缺点：

- 需要精细设计卡片与过滤器，避免“混在一起但看不懂”

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### DK-1：群组卡片统一，类型徽章区分

群组列表与搜索结果使用统一卡片骨架：

- 名称
- 类型徽章
- 简介
- 成员数
- 最近活跃
- 是否已加入
- 可选摘要

类型徽章至少支持：

- 圈子
- 学校
- 院系
- 班级
- 公司
- 部门

### DK-2：领域标签继续作为发现与推荐真相源

- `domain_taxonomy.yaml` 继续放在 `_shared/`。
- 群组发现、推荐和助理上下文继续引用同一套 taxonomy。
- 不为组织型主页单独发明第二套 taxonomy。

### DK-3：首页与搜索只讲“群组”，详情页再讲具体类型

- 首页一级入口：`群组`
- 搜索一级筛选：`群组`
- 进入详情后按模板显示为：
  - 兴趣型：圈子
  - 组织型：学校 / 院系 / 班级 / 公司 / 部门

### DK-4：详情模板只保留两类

- `通用圈子模板`
- `组织主页模板`

不继续拆出第三套“特殊模板”，避免模板爆炸。

### DK-5：助理上下文只认群组领域，不认模板差异

无论用户进入的是兴趣圈还是组织主页：

- 页面上下文继续传 `circleId`
- 助理路由继续认 `circleDomainId`
- 模板差异只影响 UI，不影响助手上下文真相源

## metadata / codegen 方案

本 L2 重点关心两类生成物：

### `_shared/domain_taxonomy.yaml`

- 继续作为群组发现、推荐、搜索筛选和助理上下文的唯一真相源

### `social/circle/*`

扩展字段与 View：

- `Circle.kind`
- `Circle.display_subject_type`
- `CircleSearchItemView`
  - 需要返回用户面向的 `groupTypeBadge`
  - 需要返回详情模板 `templateType`
- 组织型首页摘要所需的节点数量、组织摘要

### App codegen 消费

- 群组列表与搜索结果共享 typed `CircleSearchItemView`
- 不再在 UI 层维护第二套“组织和圈子”卡片模型

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- 列表卡片从“圈子卡片”演进为“群组卡片”
- 搜索结果从“圈子结果”演进为“群组结果”
- `Circle` 继续承担群组详情根模型

### 迁移 / 回填

- 现有兴趣圈数据无需迁移类型，默认 `kind=interest`
- 学校 / 公司 / 组织型主页新增时写入 `kind=organization`
- 旧的圈子频道与推荐数据沿用 taxonomy 映射，不删除历史数据

### 双读 / 双写

- 本 L2 不需要为列表发现做双读双写
- 仅在搜索结果面临时容忍旧 `CircleSearchItemView` 向新 `群组卡片` 的映射兼容

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 不新增业务 feature flag

### 观测

- `group_hub_impression_count`
- `group_hub_click_count`
- `group_hub_card_type_distribution`
- `group_hub_search_result_click_count`

### SLO 验证

- 群组发现页首屏即时可见
- 推荐结果 P95 在产品要求内返回
- 搜索到详情的点击成功率稳定

### 回滚

- 仍按整版回退
- 不保留“圈子专区 / 组织专区”并行逻辑

## TDD / ATDD 策略

- `T1_schema`
  - taxonomy
  - Circle kind / display subject type
  - 群组卡片 typed view
- `T2_module_interaction`
  - 群组列表
  - 类型徽章
  - 双模板首页切换
- `T3_cross_service_integration`
  - 推荐
  - 搜索
  - 助理上下文
- `T4_user_journey`
  - 首页进群组
  - 搜索进群组
  - 组织型详情与兴趣型详情都可稳定到达

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结群组卡片与模板相关 metadata | `T1_schema` |
| `P2` | 完成 codegen 与 typed view baseline | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地群组发现页与推荐页 | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 落地双模板详情分流与上下文继承 | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |

## 未来演进

- 若后续群组类型继续扩展，再在模板内部做模块组合，不新增第三个大模板。
- 若 taxonomy 需要运营动态下发，再从 codegen 迁到 API。
- 若组织型主页后续需要更强的身份体系，可单独拓展组织认证与导入链路。
