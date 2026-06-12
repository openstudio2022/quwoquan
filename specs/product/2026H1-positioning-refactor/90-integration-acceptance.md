# 集成验收清单（WP1–WP8 全部合入后，回主会话执行）

> 验收意图：UAT；测试证据：T4（辅 T3）
> 任一项不满足 = 集成 BLOCK，回对应需求包修复后重验。

## 1. 门禁全量

- [ ] `make verify-metadata` 绿
- [ ] `bash agent_ops/gate/gate_repo.sh --scope all` 全绿（service / data / app / portal）
- [ ] 新增门禁就位且绿：`verify-app-concept-naming`（WP5 术语门禁）
- [ ] codegen hash 比对绿（无手改产物）
- [ ] `dart analyze` 0 error / 0 新 warning

## 2. 统一性审计（人工 + 脚本）

### 2.1 统一语言

- [ ] 交集措辞全 App 仅使用六类词表（共同关注的人/圈子/兴趣/地点/校友/讨论）+ 既有事实短语；同一对象在推荐页/主页/详情页措辞一致
- [ ] 内容卡与所有内容消费面只有 `赞 / 评 / 转` 三动作；全 App 无「收藏 / 关注内容 / 稍后看」入口与文案；`favorite` 契约与代码 grep 零残留（点赞心形图标 `Icons.favorite*` 豁免）
- [ ] group 概念用户侧仅出现「讨论」；禁用词（空间/频道/论坛/群组/趣群，群概念语境）清零
- [ ] 前台无「实体」「个人主页/共享主页/关系主页」等内部词
- [ ] 我的主页无第三人称措辞（你们的连接/TA的影响）；他人/对象主页无第一人称错置

### 2.2 蓝色=连接

- [ ] 交集/连接类信息（主交集、连接计数、对象角标）统一品牌蓝 token；副交集统一灰 token
- [ ] 抽查 5 个核心页（推荐页/用户主页/实体主页/圈子主页/消息页）无大量彩色标签/图标混用

### 2.3 结构统一

- [ ] 三对象主页四段式结构一致（头部身份/连接/影响或介绍/Tab）
- [ ] 实体 Tab=内容/讨论/兴趣圈；圈子 Tab=内容/讨论/成员；标签来自 codegen 常量
- [ ] 内容卡交集理由位于图下、标题上，无图上覆盖（WP2 反断言测试在 CI 绿）

### 2.4 数据诚信

- [ ] 抽查影响模块数字（TA的影响/我的影响力/圈子影响）每条可点开枚举来源；无数据模块收起
- [ ] 交集数字与点开后的明细数一致（summary 与 points 同 snapshot）
- [ ] affinity 推荐不伪装事实措辞

## 3. T4 旅程演示（beta/gamma，经 stackctl 启动环境）

主旅程（对应概念文档 §20.1 闭环，逐环截图/录屏留证据）：

1. [ ] 推荐页看到交集 spotlight（≥3 卡非空窗）与瀑布卡交集理由（gamma 真实 API）
2. [ ] 点击带「2位校友在这里」的对象卡 → 进入实体主页 → 四段式 + 与你的连接
3. [ ] 「认识{对象名}」→ 完整介绍页（长图文/时间线/相关对象）
4. [ ] 实体主页「兴趣圈」Tab → 进入圈子主页 → 圈子影响 + 与你的连接
5. [ ] 圈子「讨论」Tab → 进入讨论会话并发言；消息页二级胶囊「讨论」可回访
6. [ ] 创作长文：行内提及对象 → 排版预览 → 发布页选标签/绑对象/绑圈子/小趣摘要 → 发布成功
7. [ ] 他人视角阅读该文：交集理由 + 提及可点；在文下评论触发「共同讨论」交集（WP1）；该文自动进入读者「我的足迹」，且足迹不产生任何交集
8. [ ] 作者「我的主页 → 我的影响力」出现可枚举增量；产生新交集后收到小趣提醒 → 跳转我的连接收件箱

辅助旅程：

- [ ] 搜索「讨论」分组正常；Web 宽屏精品按定稿规格渲染；消息页两行布局/索引/星标回归
- [ ] 登录入口双目标契约回归（`make verify-app-login-entry-loop-contract`）

## 4. 文档与 CR 收口

- [ ] 各包 dev_log（含 verify 命令证据）已追加至 `CR-20260611-033`
- [ ] 受影响 spec 修订完成：`object-homepage-network`、`commercial-message-system`、`content-display-journey-consistency`、`profile-homepage-redesign`（Tab 措辞裁决）
- [ ] 页面矩阵 + `metadata_driven_ui_gap_inventory` + PR checklist 与磁盘一致（gate 已覆盖，人工复核新增行）
- [ ] `journey_scenario_registry.yaml` 如有 journey 增改已登记
- [ ] CR-20260611-033 状态推进至 implemented

## 5. 遗留与后置项登记（验收时确认仍在 convergence 清单）

- 校友图谱（共同校友的图谱级计算）
- 实体页影响卡（homepage_impact，视数据可用性）
- 消息页五个一级分类方案（如商用后数据证明二级承载不足再评估）
- `works_immersive_viewer.dart` / `article_read_only_book_deck.dart` 等超大文件的持续拆分
