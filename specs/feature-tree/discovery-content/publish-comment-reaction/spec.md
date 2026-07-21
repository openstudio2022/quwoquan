# L2 特性：publish-comment-reaction

## 功能说明

内容发布、评论互动、反应计数与行为上报的端云协同能力。

### 子特性

| 子特性 (L3) | 说明 | 状态 |
|-------------|------|------|
| **comment-thread** | 商用级评论系统：2 级层级、多入口统一评论面、hot/latest 两档服务端排序、评论赞踩、图片与 @ 输入、置顶、举报与治理状态机、IP 属地与作者赞过/关系标签投影、个人主页评论管理、Persona 身份、10 万+容量承载、端云配置统一 | V4 规格已冻结（2026-07-20） |
| post-create-update | 发布/更新/删除帖子 | 已实现 |
| **text-post-commercial-publication** | 写文字从正文优先编辑、显式 micro/article 确认、发布前安全准入、可靠意图队列到发布结果回流、交集事实和运营漏斗 | 商用收口中（2026-07-20） |
| **image-editing** | 照片发布前的纯端侧像素编辑：零占位工具、统一像素引擎、文件快照撤销/重做、放弃保护与页面观测；完成后仅把本地结果交回 MediaUploadSession 链路 | 本地商用基线已实现（2026-07-20） |
| **filter-catalog-release** | 不可变滤镜目录发布：Data publish Stage/Activate/Rollback、public typed Reader、App verified cache 与同源 bootstrap replica | 端云实现与本地契约已完成；四环境发布/UAT 证据收集中（2026-07-21） |
| reaction-state-counter | 点赞/收藏/分享计数与一致性 | 已实现 |
| 行为上报 | ReportBehaviors（impression/click/dwell/dislike/report/share/comment） | 已实现 |

### 评论端云一体化（V4 2026-07-20）

comment-thread 为端云一体的完整评论体验，覆盖：

- **核心交互**：2 级层级、多入口打通（feed 卡片弹窗/沉浸式上压/个人互动）、游标分页、hot/latest 两档服务端排序、回复分页、评论赞踩、删除审计、长评论折叠、作者标识、相对时间
- **治理合规**：`active/hidden/deleted/tombstoned` 状态机、评论级举报（Report target=comment）、operator 治理命令与审计事实、CreateComment 频控、IP 属地快照展示
- **展示投影**：作者赞过（`authorLiked`）、viewer 关系标签（`viewerRelation`：following/friend 事实投影）——趣我圈交集差异化在评论区的落点
- **扩展功能**：Persona 身份切换、个人主页"我发出的/收到的评论"、字数限制端云一致、评论/回复/@/置顶通知、图片附件、emoji 与 @ 输入（关注候选选择器）、登录续接、评论深链定位
- **行为回流**：评论创建成功经 `trackComment` 回流推荐 HotPath（weight 2.5）
- **非功能规格**：首屏 P95 < 800ms、提交 P95 < 500ms、10 万+评论容量、乐观更新 + 最终一致、弱网降级、hotScore 投影收敛 SLI
- **配置统一**：业务规则参数（字数限制/回复预览/回复展开/默认排序/附件上限/频控窗口）统一由 config.yaml 管理，端侧通过 App Config 同步
- **灰度发布**：Canary → 1% → 50% → 100% 四阶段，SLO + 回滚条件

详见 `comment-thread/spec.md`（V4）与 `comment-thread/acceptance.yaml`。

## 约束

- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。
- 写文字创作漏斗属于产品遥测，不得伪装成推荐行为写入 `ReportBehaviors`。
- Post 远端提交态只允许 `pending_review/published/rejected/deleted`；安全准入不确定时
  只能进入不可公开 pending_review 和人工 Case，禁止绕过安全门。
- micro/article 可以由系统建议，但最终类型必须由用户在发布确认页显式确认。
- 评论域业务参数不允许硬编码，必须走 config.yaml 统一管理。
- 图片编辑会话是 App runtime session，不创建远端草稿聚合；编辑完成前不调用云端，
  完成后只经 `MediaUploadSession → MediaAsset → Post` 单轨交接。
- 图片编辑器所有对用户可见的变换必须经 `ImageEditorExportEngine`；预览、导出、诊断
  和像素测试不得维护第二套几何或局部效果近似。
- Comment 是独立聚合（`content/comment/entity.yaml`），仅通过 postId 引用 Post；Post 删除通过 PostDeleted 事实驱动评论批量 tombstone 级联，不存在同事务 cascade_delete。
- 排序真相源唯一在服务端（hotScore 投影 + 复合索引）；禁止端侧重排、禁止旧三档 `recommended/latest/most_liked` 回归、禁止 Redis 排行第二真相源。

## 验收标准

- A1：发布、评论、互动、行为上报功能路径可执行且输出稳定。
- A7：契约一致性校验通过（metadata ↔ OpenAPI ↔ service.yaml ↔ 端侧 typed Facet）。
- A8：对应自动化测试映射完整。
- 评论详细验收标准见 `comment-thread/acceptance.yaml`。
- 写文字商用验收见 `text-post-commercial-publication/acceptance.yaml`。
- 图片编辑本地 GWT 与图片创作组合 SIT 见 `image-editing/acceptance.yaml` 和本能力
  `acceptance.yaml#SIT3`。
- 滤镜目录发布、离线副本与回滚验收见 `filter-catalog-release/acceptance.yaml`。

## 适用范围与约束

- 适用：所有内容类型（微趣/图片/视频/文章）的社交互动能力
- 不适用：内容推荐算法（归属 feed-orchestration-recommendation）、社交关系写模型（归属 user-identity-profile-relationship；本能力只消费 persona_follow_projection 事实投影）
