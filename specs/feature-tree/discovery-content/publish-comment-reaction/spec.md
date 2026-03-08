# L2 特性：publish-comment-reaction

## 功能说明

内容发布、评论互动、反应计数与行为上报的端云协同能力。

### 子特性

| 子特性 (L3) | 说明 | 状态 |
|-------------|------|------|
| **comment-thread** | 商用级评论系统：2 级层级、8 入口全通、热评/最新排序、评论点赞、个人主页评论管理、先发后审、Persona 身份、10 万+容量承载、端云配置统一 | V1 PRD 已基线化 |
| post-create-update | 发布/更新/删除帖子 | 已实现 |
| reaction-state-counter | 点赞/收藏/分享计数与一致性 | 已实现 |
| 行为上报 | ReportBehaviors（impression/click/dwell/dislike/report/share） | 已实现 |

### 评论端云一体化（V1 PRD 2026-03-08）

comment-thread 已从最初的基础 CRUD 骨架扩展为商用级全量评论系统，覆盖：

- **核心交互**（F1~F14）：2 级层级、8 入口打通、评论弹窗 UI、游标分页、热评/最新排序、回复折叠、评论点赞、删除审计、长评论折叠、作者标识、相对时间
- **扩展功能**（F15~F20）：先发后审、Persona 身份切换、个人主页"我发出的/收到的评论"、字数限制端云一致、评论通知骨架
- **非功能规格**：首屏 P95 < 800ms、提交 P95 < 500ms、10 万+评论容量、乐观更新 + 最终一致、弱网降级、热帖缓存防护
- **配置统一**：业务规则参数（字数限制/热帖阈值/缓存 TTL）统一由 config.yaml 管理，端侧通过 App Config 同步
- **灰度发布**：Canary → 1% → 50% → 100% 四阶段，SLO + 回滚条件

详见 `comment-thread/spec.md` 与 `comment-thread/acceptance.yaml`（A1~A23）。

## 约束

- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。
- 评论域缓存参数不允许硬编码，必须走 config.yaml 统一管理。
- Comment 为 Post 聚合成员，生命周期由 Post 管控（cascade_delete）。

## 验收标准

- A1：发布、评论、互动、行为上报功能路径可执行且输出稳定。
- A7：契约一致性校验通过（metadata ↔ OpenAPI ↔ service.yaml ↔ 端侧 Repository）。
- A8：对应自动化测试映射完整。
- 评论详细验收标准见 `comment-thread/acceptance.yaml` A1~A23。

## 适用范围与约束

- 适用：所有内容类型（微趣/图片/视频/文章）的社交互动能力
- 不适用：内容推荐算法（归属 feed-orchestration-recommendation）、社交关系（归属 social-graph）
