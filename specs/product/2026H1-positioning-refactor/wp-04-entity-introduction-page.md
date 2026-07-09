# WP4 · 实体完整介绍页（端云）

> 树归属：`shared-homepage-network/homepage-review-and-content-journey`（L2 延伸）
> 影响 Journey：`content-discovery-to-consumption`、`external-acquisition-and-deeplink`
> 验收意图：GWT + contract；测试证据：T1 / T2 / T3

## 1. 背景与现状

- 实体主页（`lib/ui/entity/widgets/homepage_detail_shell.dart`）已有 summary 卡 + 内容/讨论/兴趣圈 Tab，但无「百科式介绍」承载：规格要求主页只展示摘要、点击进入完整介绍页（800+ 字图文、时间线、地图、相关人物/实体、历史沿革、核心信息）。
- 云侧 `contracts/metadata/entity/homepage/` 域完备（aggregate/fields/service/projections），但无 introduction 投影与对应路由。
- 数据工程 `qwq-data` CLI 管线可生产真实图文内容，可作为实体介绍内容供给来源。
- 前台命名约束：不暴露「实体」一词，页面标题为「认识{对象名}」或对象名本身。

## 2. 功能规格

### 2.0 统一概念基线（基线已落地，引用词典；本包防回归）

> 收藏概念已由「持续连接基线修正」会话全仓退场，本节按防回归口径执行。本包无 WP1 前置依赖（`homepage_introduction` 投影确认仍属本包）。

- 实体介绍页是“认识这个对象”的长期知识页面，不承接“收藏夹”心智。
- 用户如果想把某个对象纳入未来决策或持续跟进，唯一动作是 `关注`（实体右侧关注按钮），进入“我的关注”；不存在“收藏对象”或“关注内容”表达。
- 与实体介绍页相邻的对象主页、交集卡、影响卡只用六个母表达与词典注册表 kind；涉及内容相关理由时用 `共同讨论` 等连接型表达。

### 2.1 介绍内容模型（metadata-first）

- entity homepage 域新增 `homepage_introduction` 投影：
  - `homepageId`、`summary`（主页摘要，2~3 行）、`sections[]`（结构化分节：`{kind, title, body(markdown), assets[]}`，kind 闭集建议 `overview | timeline | keyFacts | relatedPeople | relatedObjects | history`）、`updatedAt`、`sourceRefs`（内容溯源，对齐数据工程真实性约束）。
  - 时间线为 sections 的一种 kind（`timeline`：items `{date, text, assetUrl?}`），不另造对象。
- service.yaml 新增 `GetHomepageIntroduction`（读路径）；写路径首发走数据工程供给 + 维护后台，不开放端侧编辑。

### 2.2 介绍页（新页面）

- 路由/surface 经 metadata（`ui_surfaces`/route 真相源）→ codegen，新路由形如 `homepage introduction` 语义；禁止硬编码 path。
- 页面结构：沉浸头图（复用对象头图）→ 摘要 → 分节长图文（markdown 渲染复用阅读侧能力）→ 时间线 → 相关人物/相关对象（横滑卡，点击跳对应主页）→ 底部「内容 / 讨论 / 兴趣圈」回流入口。
- 深链支持：介绍页可被分享/外链直达（对齐 `external-acquisition-and-deeplink`）。
- 埋点（R20/R21）：曝光、停留、阅读深度、referralSource 必传。

### 2.3 与 WP3 的边界

- WP3 在实体主页 summary 卡做「认识{对象名}」摘要 + 查看更多入口（消费本包 codegen 路由常量与 `summary` 字段）。
- 本包只新增 `lib/ui/entity/pages/` 下介绍页文件与 providers，不改 `homepage_detail_shell*.dart`（归 WP3）。

### 2.4 数据供给

- fixtures：≥1 个完整实体介绍样本（含全部 section kind）进 contract fixtures + alpha/beta seed manifest。
- 真实内容：以 `qwq-data` 管线为介绍内容生产入口的对接说明（产出 → entity 域导入），首发可人工导入 beta seed。

## 3. 周边契约

- 投影/路由/surface 全部 metadata-first；`GetHomepageIntroduction` 响应经统一 `CloudResponseDecoder`。
- Repository 扩展遵循 R02（≤10 方法/接口，必要时新子接口 `HomepageIntroductionRepository`）+ 三层模式（Abstract/Mock/Remote）+ `app_providers.dart` 注册。
- 新增文案 key 追加 `UITextConstants`，登记于此：（细化会话填写）。

## 4. 改动范围

- `contracts/metadata/entity/homepage/`（projections/homepage_introduction.yaml、service.yaml、ui_config/route）
- `quwoquan_service/services/entity-service/`（introduction 读路径 + 存储）
- `quwoquan_app/lib/cloud/services/`（entity 域 repository 扩展，三层）
- `quwoquan_app/lib/ui/entity/pages/homepage_introduction_page.dart`（新）+ providers
- `quwoquan_app/lib/app/navigation/`（路由注册，经 codegen 常量）
- 页面矩阵 + `metadata_driven_ui_gap_inventory` 新行

## 5. 准出要求

1. T1：introduction 投影契约测试（section kind 闭集、markdown 往返、sourceRefs 非空）。
2. T2：介绍页 widget 测试（摘要/分节/时间线/相关对象渲染、空 section 容错、错误态结构化）。
3. T3：beta 环境从实体主页摘要进入介绍页，渲染真实样本；深链直达可用。
4. 新页面登记页面矩阵 + gap inventory + PR checklist；曝光/停留/深度埋点齐备。
5. `make verify-metadata`、`bash quwoquan_ops/gate/gate_repo.sh --scope app` 与 `--scope service` 全绿。
6. 前台文案无「实体」字样（§18 禁用词约束）。

## 6. 验收标准（GWT 样例）

- Given 清华大学主页配置了完整介绍，When 点击「认识清华大学 → 查看更多」，Then 进入介绍页，含 800+ 字图文、时间线与相关对象横滑，且可经分享链接直达。
- Given 介绍页底部回流入口，When 点击「兴趣圈」，Then 回到实体主页对应 Tab。
- Given 某对象无介绍数据，Then 主页摘要模块收起，介绍页路由直达时展示结构化空态（非报错）。
