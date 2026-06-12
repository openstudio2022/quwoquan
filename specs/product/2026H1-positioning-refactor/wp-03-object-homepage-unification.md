# WP3 · 三对象主页结构统一与影响模块（端云）

> 树归属：`object-homepage-network`（L1 收口层）+ `user-identity-profile-relationship/profile-homepage-redesign` + `circle-community/circle-experience-redesign/circle-homepage-redesign` + `shared-homepage-network`
> 影响 Journey：`content-detail-profile-handoff`、`message-social-connection`
> 验收意图：SIT + GWT；测试证据：T1 / T2 / T3

## 1. 背景与现状

- 三主页骨架已落地：`ObjectPageShell` 三壳（full/standard/minimal）、统一交集卡 `ObjectIntersectionCard`（你们的连接 / 你和这里的交集 / 你认识的人在这）、用户主页影响卡 `AuthorImpactCard`（我的影响力 / TA的影响）。
- 缺口：
  - 三主页 header/看点区/行动入口**视觉尚未统一**（`object-homepage-network/spec.md` 自述）；
  - 影响模块仅用户主页有，圈子页无「圈子影响」、实体页无介绍/影响模块；
  - 实体壳（`homepage_detail_shell.dart`）与圈子壳（`circle_shell.dart`）Tab 标签硬编码中文（'内容'/'讨论'/'兴趣圈'/'成员'），未走 metadata codegen（违反 R06/R27 方向）；
  - 连接模块标题措辞分散（你们的连接 / 你和这里的交集 / 你认识的人在这），需统一为「连接」族口径；
  - 用户主页 Tab 标签「作品/看点」与 V5 spec「创作/生活」存在措辞漂移（细化会话内裁决并同步 spec）。

## 2. 功能规格

### 2.0 统一概念基线（本包必须遵守）

- 对象主页的“连接”与“影响”必须遵守新的动作基线：`认同（赞）/ 交流（评）/ 传播（转）/ 持续连接（关注人、关注实体、加入圈子）`；内容不提供长期动作。
- 影响模块不得出现“收藏了我的内容”“持续关注了我的内容”类内容沉淀表达；只用连接型表达：“进入了相关圈子”“建立了新连接”“开始关注这个对象”“带来了新讨论”。
- 对象页交集表达只用六个母表达与词典注册表 kind；内容维度交集由 `共同讨论` 等连接型表达承载。

### 2.1 四段式结构统一（概念文档 §20.5）

用户 / 我的 / 实体 / 圈子主页统一为：

```text
头部身份：封面图 + 头像 + 名称 + 身份标签单行（· 分隔）+ slogan/简介 + 操作按钮
连接模块：纵向列表 ≤3 条结论句 + 「查看更多」；统一交集卡同源
影响 / 介绍模块：用户=影响力卡；圈子=圈子影响；实体=「认识 + 对象名」摘要卡
Tab 内容区：用户=作品/圈子/互动/看点；实体=内容/讨论/兴趣圈；圈子=内容/讨论/成员
```

- 头部视觉统一：实体页升级为与用户/圈子同级的沉浸头图形态（封面 + 渐变 + 头像/Logo 侵入），由 `ObjectPageShell` 统一承载。
- 连接模块标题统一：他人主页=「你们的连接」、实体页=「与你的连接」、圈子页=「与你的连接」（替换「你认识的人在这」，保留其作为副标题语料的可能，细化会话定稿）；我的主页=「我的连接」（交集收件箱入口）。
- 第一人称约束：我的主页禁止出现「你们的连接 / TA的影响」，新增反断言测试。

### 2.2 影响模块扩展（云侧投影 + 端侧卡片）

新增两个投影（对齐既有 `author_impact_summary/item` 形状，复用 item 结构）：

- `circle_impact_summary`：`{circleId, total, items[{helpType, action, intersectionDimension, tagRef, source, count, displayText}]}`，示例 displayText：「328人通过这里建立了新连接」「189人加入相关圈子」「42个地方和事物正在被讨论」（最后一条前台文案不出现「实体」字样，细化会话定稿）。
- `homepage_impact_summary`：实体页可选（首发可只做「认识这个对象」摘要卡，影响卡视数据可用性决定）。

约束（概念文档 §20.3）：每条 displayText 必须可枚举来源（点开见明细或跳交集列表）；云侧无真实归因数据时不下发该条；端侧空态收起（mine 态可显示鼓励文案，对齐 AuthorImpactCard 现状）。

### 2.3 「认识这个对象」摘要卡（实体页）

- summary 卡内新增介绍摘要模块：标题「认识{对象名}」+ 2~3 行摘要 + 「查看更多」。
- 「查看更多」跳转 WP4 的实体介绍页路由（路由常量来自 WP4 codegen；WP4 未合入前入口隐藏/置灰，以 feature 判断介绍内容是否存在为准）。

### 2.4 Tab 标签 metadata 化

- 实体壳/圈子壳的 Tab 标签收口到 metadata（`entity/homepage/ui_config` 与 circle 域对应 ui_config）→ codegen 常量，禁止壳内中文字面量。
- 标签终值：实体=`内容 / 讨论 / 兴趣圈`，圈子=`内容 / 讨论 / 成员`（与 §18「讨论」命名一致，WP5 改的是 chat/搜索域，此处本来就叫讨论，无冲突）。

## 3. 周边契约

- 影响投影 yaml 形状以本简报 §2.2 为冻结契约；落地顺序 metadata → `make verify-metadata` → `make codegen-app` → 业务。
- 交集卡数据契约不动（与 WP1 解耦）；WP1 会移交「新 kind → rank/icon/维度短语」映射清单，由本包在 `evidence_group.dart` 实现。
- `lib/components/object_page/**` 本包独占；其他包对该目录的需求一律走清单交接。
- 新增文案 key 追加 `UITextConstants`（连接模块标题、圈子影响标题、认识对象标题等），登记于此：（细化会话填写）。

## 4. 改动范围

- `quwoquan_app/lib/components/object_page/**`（壳、交集卡标题、影响卡组件泛化、evidence_group 扩展）
- `quwoquan_app/lib/ui/user/widgets/`（profile_shell/header/builders 对齐四段式、措辞核对）
- `quwoquan_app/lib/ui/circle/widgets/circle_shell.dart`（圈子影响模块 + Tab metadata 化）
- `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell*.dart`（头部统一 + 认识摘要卡 + Tab metadata 化）
- `contracts/metadata/`：circle/entity 域影响投影 + ui_config Tab 标签
- 云侧：circle 域与 entity-service 影响聚合读路径（基于既有计数/事件投影聚合）
- 对应 spec 修订：`object-homepage-network/spec.md`、`profile-homepage-redesign/spec.md`（Tab 措辞裁决）

## 5. 准出要求

1. T1：circle_impact / homepage 介绍摘要投影契约测试（字段、displayText 非空即可枚举语义）。
2. T2：三主页 widget/golden 测试断言四段式结构与统一标题；我的主页第三人称反断言。
3. T2：影响卡三态（有数据 / 空收起 / mine 鼓励文案）。
4. T3：beta 环境三主页真实数据渲染（连接模块与影响模块非 mock）。
5. 页面矩阵对应行更新；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿（含 Tab 标签无硬编码中文的语义检查）。
6. 实体/圈子壳中不再有 Tab 中文字面量（codegen 常量化）。

## 6. 验收标准（GWT 样例）

- Given 同一用户依次打开 他人主页 / 实体主页 / 圈子主页，Then 三页均为四段式结构，连接模块均为纵向 ≤3 条 + 查看更多，标题分别为「你们的连接 / 与你的连接 / 与你的连接」。
- Given 我打开我的主页，Then 出现「我的连接」「我的影响力」，且全页无「你们的连接 / TA的影响」字样。
- Given 圈子有真实归因数据，Then 圈子影响显示 ≤3 条结论句且每条可点开枚举；无数据时该模块整体不渲染。
- Given 实体配置了介绍摘要，Then summary 卡显示「认识{对象名}」+ 摘要 + 查看更多；未配置则模块收起。
