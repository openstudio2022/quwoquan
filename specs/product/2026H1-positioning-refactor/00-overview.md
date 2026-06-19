# 2026H1 商用定位与 UX 重构：需求包总纲（WP0–WP8）

> 状态：冻结（WP0 完成即生效）
> 概念真相源：`specs/00_PRODUCT_CONCEPT_SYSTEM.md` §20、`specs/00_GLOBAL_TERMINOLOGY.md` §18
> 交集词典真相源：`specs/product/intersection-definition-and-application.md`
> CR：`specs/changelog/CR-20260611-033-commercial-positioning-ux-refactor-program.yaml`
> 集成验收：本目录 `90-integration-acceptance.md`

---

## 1. 目标

围绕「交集驱动的同趣连接网络」定位，完成商用上线前的产品概念统一、交集表达升级、三类主页结构统一、讨论命名收口、创作链路增强与小趣贯穿，达到可直接与微信 / 小红书形成差异化竞争的体验完整度。

## 2. 规格合理性分析结论（已冻结的修正项）

| 规格原文 | 结论 | 修正口径 |
|---|---|---|
| 交集六类「共同X」表达 | 采纳，修正落点 | 落在证据组 kind + 云侧 `primaryText` 层，**不动 5 维闭集**，G2（端不拼装）不变；完整边界、关系语言与 kind 唯一注册表以 `specs/product/intersection-definition-and-application.md` 为准 |
| 共同校友 | 采纳，降级首发 | 首发以「同校」entity tagRef 事实落地，校友图谱后置 |
| 收藏体系 | 全量退场（不留兼容） | 内容主互动只有 `点赞 / 评论 / 转发`，内容**不提供任何长期动作入口**（无收藏、无关注内容、无稍后看）；持续连接只针对对象（关注人 / 关注实体 / 加入圈子）；「以后再看」由 `我的足迹`（自动记录，私有，不产生交集）承载；`favorite` 契约、API、行为信号、UI 入口全链路退场，退场清单见 `specs/product/intersection-definition-and-application.md` |
| 消息页五分类（消息/联系人/圈子/讨论/小趣） | 修正 | 保留已冻结「消息/联系」双 Tab，五分类语义落二级胶囊；小趣维持全局顶栏入口 |
| 「实体」概念 | 采纳，前台不暴露词 | 实体=共享主页的概念/PRD 名，前台仍用对象名；「认识这个实体」前台文案为「认识 + 对象名」 |
| 影响模块数字 | 采纳 + 硬约束 | 必须满足交集四条件（可证/可枚举/可解释/可行动），无真实归因则收起，禁止伪造 |
| 推荐页卡结构 / spotlight 3~3.5 卡 | 现状已达标 | 固化为契约测试，重点转向真实环境数据质量（gamma 空窗治理） |
| 长文编辑三段式（编辑/排版预览/发布） | 现状已达标 | 增量在标签/实体绑定、AI 摘要、行内提及、小趣辅助 |

## 3. 需求包索引与依赖

```text
WP0（本文档所在基线，已完成）
  ├─→ WP1 交集事实数据源与表达升级（云侧主导）      wp-01-intersection-data-and-expression.md
  ├─→ WP2 发现页交集呈现与内容卡统一（端侧）        wp-02-discovery-intersection-presentation.md
  ├─→ WP3 三对象主页结构统一与影响模块（端云）      wp-03-object-homepage-unification.md
  ├─→ WP4 实体完整介绍页（端云）                    wp-04-entity-introduction-page.md
  ├─→ WP5 「讨论」命名统一与消息页 IA（端云）       wp-05-discussion-naming-and-message-ia.md
  ├─→ WP6 长文编辑与发布增强（端侧为主）            wp-06-article-editor-and-publish.md
  ├─→ WP7 精品页统一（端侧，小包）                  wp-07-featured-page-unification.md
  └─→ WP8 小趣贯穿强化（assistant 端云）            wp-08-assistant-throughline.md

解耦边界（保证并行）：
  WP1 ↔ WP2：经 IntersectionReason DTO 现有字段解耦（WP1 不改 DTO 形状，WP2 不依赖云侧新数据，先用 mock seed）
  WP3 ↔ WP4：WP3 只做「认识这个对象」摘要卡 + 入口占位；介绍页本体、路由、投影归 WP4
  WP6 ↔ WP8：经 WP0 冻结的 assistant 创作辅助 API 契约解耦（WP8 未就绪时 WP6 入口置灰降级）

WP1 内部子序列（详见 wp-01 §2.5，可并行）：
  WP1·T1~T4（云侧 kind 收尾 + 六类数据源 + 空窗治理 + mock/fixtures 标准化）——先行序列
  WP1·T5（足迹端侧消费闭环：Repository 三层 + 足迹列表页）——独立子序列，可与 T1~T4 并行
  WP1·T6（kind→rank/icon/维度短语映射清单，wp-01 附录 A）——WP3 evidence_group 扩展的交接物

跨包依赖顺序补注：
  WP2 开发期依赖 WP1·T4（端侧 mock kind 标准化）先行，否则开发期展示出现旧 kind 样本；beta 联调依赖 WP1·T2/T3
  WP3 的 evidence_group.dart 扩展依赖 WP1·T6 映射清单（已随 wp-01 附录 A 交付为规格态）
  WP8 新交集提醒依赖 WP1·T2；「引导到我的足迹」依赖 WP1·T5
```

## 4. 跨包统一约束（每个细化会话开场必读）

1. **军规全集生效**：metadata → verify → codegen → 业务 → test → gate；codegen 产物禁手改；R01–R32 全部适用。
2. **文件独占权**（防并行冲突，越权改动=集成验收 BLOCK）：
   - `quwoquan_app/lib/components/object_page/**` → 仅 WP3 可改。
   - `lib/core/constants/ui_text_constants.dart` / `app_concept_constants.dart` 的**批量改名** → 仅 WP5；其他包只允许**追加**新 key（不改既有 key 值），并在本包简报「新增文案 key」清单登记。
   - `contracts/metadata/recommendation/rec_model/projections/intersection_reason.yaml` → 交集统一规格收口（2026-06）允许字段形状一次性收敛（删除 displayText/label/sharedCount）；词表与 G2 以概念文档 §18 为准。
   - `lib/ui/chat/**` 与 `messages/conversation` metadata → 仅 WP5。
   - `lib/ui/discovery/**` → 仅 WP2（WP7 例外：`works_immersive_viewer.dart` 归 WP7）。
   - `lib/ui/content/entry/**` 与 `markdown/**` → 仅 WP6。
   - `lib/ui/entity/**` → WP3 改 `widgets/homepage_detail_shell.dart` 系列；WP4 只新增 `pages/` 介绍页文件，不改既有壳。
   - `lib/ui/user/pages/` 的**足迹列表页新文件** → 归 WP1（T5 足迹端侧闭环）；WP3 独占的是 `lib/components/object_page/**` 与 `lib/ui/user/widgets/`，二者目录不相交，不构成冲突。
3. **统一语言与视觉**：交集措辞只用 §20.3 六个母表达与 `specs/product/intersection-definition-and-application.md` 词典口径；内容互动只有 `赞 / 评 / 转`，禁止在任何新增规格中引入 `收藏 / 关注内容 / 稍后看` 等内容长期动作；持续连接只针对对象（关注人 / 关注实体 / 加入圈子），「以后再看」由我的足迹承载；连接类信息一律 `AppColors` 品牌蓝 token；新增用户可见文案禁用 §18.3 禁用词。
4. **页面横向质量**：新增/改动页面文件必须同步页面矩阵 + `metadata_driven_ui_gap_inventory` + PR checklist + 埋点（R20/R21）。
5. **数据**：alpha mock 改动必须先进 contract fixtures + `app_alpha_seed_manifest.json`；beta/gamma 演示数据进对应 seed manifest。
6. **CR**：每包完成后在 `CR-20260611-033` 的 `dev_log` 追加条目（date / change / verify 命令证据），不另开 CR（除非范围超出本总纲）。
7. **提交**：每包独立分支或独立提交序列，提交信息前缀 `wp{N}:`，便于集成会话审阅。

## 5. 独立会话开场模板

拷贝以下文本到新会话即可启动某个需求包：

```text
请实现需求包 WP{N}。
真相源与边界：
1. 先读 specs/product/2026H1-positioning-refactor/00-overview.md（跨包约束与文件独占权）
2. 再读 specs/product/2026H1-positioning-refactor/wp-0{N}-*.md（本包功能规格/契约/准出/验收）
3. 概念与术语以 specs/00_PRODUCT_CONCEPT_SYSTEM.md §20、specs/00_GLOBAL_TERMINOLOGY.md §18 为准
4. 交集完整词典、关系语言规则、standard kind 与别名退场迁移以 specs/product/intersection-definition-and-application.md 为准
严格按包内「准出要求」自验全绿后，把 dev_log 证据追加到 CR-20260611-033。
不得越界改动其他包独占文件；需要跨包契约变更时停下来说明，不要私自扩散。
```

## 6. 集成验收

全部包合入后回到主会话，按 `90-integration-acceptance.md` 执行：gate 全量、统一性审计清零、T4 旅程演示（beta/gamma）、CR 关闭。
