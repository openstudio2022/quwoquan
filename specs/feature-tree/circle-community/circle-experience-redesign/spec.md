# L2 规格：圈子体验重构

## 背景与动机

当前圈子发现体验依赖硬编码的兴趣维度分类（遇见/校园/车友/人文/生活/运动/科技/旅行/美食），与个人助理的领域路由体系完全独立。用户在不同场景下获得割裂的领域体验——助理中聊旅行规划，但圈子推荐与旅行无关联。

本 L2 目标：建立统一领域标签体系，重构圈子发现逻辑，让用户在圈子中找到同频社区。

## 目标用户

- 新用户：需要高效发现感兴趣的圈子，减少筛选成本。
- 活跃用户：期望圈子推荐与自身兴趣动态同步。
- 助理用户：在助理对话中自然关联到相关圈子。

## 功能范围

### L3: domain-taxonomy-alignment（领域标签对齐）
- 建立 domain taxonomy 配置文件，定义统一领域 ID 及其属性。
- 圈子频道分类从硬编码 Map 迁移为 taxonomy 驱动。
- 个人助理 domain_routing_catalog.json 引用同一套领域 ID。
- 领域 ID 至少覆盖：travel, local_life, health_wellness, tech, education, lifestyle, social_meet, culture_arts, automotive, finance, fortune。

### L3: resonance-discovery（同频发现）
- 用户兴趣画像聚合（助理交互领域频次 + 内容浏览标签 + 圈子参与历史）。
- 基于兴趣画像的圈子推荐排序。
- 圈子列表页「推荐」频道由同频推荐驱动。

### L3: circle-homepage-redesign（圈子主页端云一体化交付）
- 圈子详情页 CircleShell 布局重构（对标 ProfileShell）：NestedScrollView + SliverAppBar + 下拉弹簧拉伸 + 吸顶过渡。
- "作品"Tab 更名为"创作"，新增二级 SubTab（全部/微趣/图片/视频/文字），对标 ProfileCreationsTab。
- CircleStateNotifier 状态管理（替代 setState），Circle DTO 类型化（替代 Map<String, dynamic>）。
- 板块独立加载与降级，Mock 依赖解除。
- 云侧 GetCircleFeed stub 补全，四层测试覆盖，部署就绪。

## 不做什么（Out of Scope）

- 不实现推荐算法的训练流水线（仅做接口与排序策略）。
- 不修改个人助理引擎核心——仅在路由层传入圈子领域上下文。

## 约束

- 领域标签统一配置必须为 metadata YAML，经 codegen 生成端云代码。
- 兼容现有圈子分类——旧分类 ID 映射到新领域 ID，不删除旧数据。
- 推荐排序必须支持降级到按热度排序（推荐服务不可用时）。

## 验收重点

- A3（L1）：统一领域标签体系建立，至少 5 个领域对齐。
- A4（L1）：圈子详情页板块式重构，4 个功能区独立加载。
- A9（L1）：同频发现推荐可用，相关度 ≥ 60%。
