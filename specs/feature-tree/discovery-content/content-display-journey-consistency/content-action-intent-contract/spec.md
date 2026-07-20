# L3 特性：content-action-intent-contract（8 类反馈闭环契约）

## 功能说明

将单条内容上的 8 类反馈统一收敛为可验证闭环：`like`、`favorite`、`share`、`comment`、`dislike`、`report`、`block user`、`block keywords`。闭环定义为：端侧触发 → 云侧可接收 → 推荐链路可生效 → 持久化与计数可对账 → 测试可回归。

## 职责边界

- **负责**：
  - Discovery 侧反馈入口统一接入 Provider/Repository（Works + Moment）。
  - `POST /content/behaviors`（批量行为）与专用路由（like/favorite/comment/report）边界清晰化。
  - 用户域反馈（`block user`、`block keywords`）与推荐过滤语义对齐。
  - 举报理由、举报人私有进度查询、结案通知与运营审核回流。
  - 更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
  - metadata 对齐：`behaviors.yaml`、`user_profile/fields.yaml`、相关 service/events 契约。
- **不负责**：
  - 推荐模型参数调优（仅完成信号打通，不做权重实验结论）。
  - 打赏、会员、虚拟币等交易能力；未完成 R-LEGAL-001 前不得展示入口。
  - 通用 App 意见反馈；该能力应在帮助与反馈业务对象中独立规划，不挂靠 Post 负反馈。

## 8 类反馈对象映射

1. `like`：内容域显式正反馈（专用路由）。
2. `favorite`：内容域显式正反馈（专用路由）。
3. `share`：内容域强正反馈（batch 行为）。
4. `comment`：内容域强正反馈（专用路由 + commentLength 特征）。
5. `dislike`：内容域显式负反馈（batch 行为）。
6. `report`：内容治理负反馈（举报实体 + 推荐负信号桥接）。
7. `block user`：用户域负反馈（block_edge，跨内容过滤）。
8. `block keywords`：用户域偏好过滤（UserSetting 新字段）。

## 适用范围与约束

- **适用**：`content-display-journey-consistency` 下 photo/video/article/moment 全链路反馈。
- **约束**：
  - `like/favorite/comment/report` 走专用路由，禁止混入 batch tracker。
  - `impression/click/dwell/share/dislike` 走 `ContentBehaviorTracker` 批量缓冲。
  - `block keywords` 必须 metadata-first，先补 `UserSetting.blockedKeywords` 再接 UI。
  - 推荐实时链路依赖 `sessionId`，端侧 headers 必须稳定注入。
  - Post 举报必须先选择 metadata `ReportReason`，不得固定提交 `other`。
  - 举报进度只允许 reporter 本人读取，不暴露 reviewerId、内部处置细节或其他举报人。
  - `block user` 文案必须明确表达“拉黑”及其影响，不能用轻量措辞包装重操作。
  - `block keywords` 必须由用户确认具体词，并提供查看、删除与恢复入口。

## 与父/子节点关系

| 节点 | 关系 |
|------|------|
| `content-display-journey-consistency`（L2） | 父节点 |
| `feed-orchestration-recommendation`（L2） | 依赖其推荐引擎读取 session signals |
| `publish-comment-reaction`（L2） | 依赖其反应计数与评论主链路实现 |

## 验收标准概要

- A1：8 类反馈均有明确路由与业务对象归属，无歧义。
- A2：`dislike/share/impression/dwell/click` 可进入 HotPath Redis 并影响下一次推荐。
- A3：`like/favorite/comment/report` 专用路由语义与 metadata 一致。
- A4：`block user` 可驱动内容过滤；`block keywords` 可持久化到用户设置。
- A5：端侧反馈入口无空回调、开发中 toast 或点击即关闭的假成功；延期能力不展示。
- A6：计数链路（like/favorite/comment/share/view）具备对账策略与契约测试。
- A7：L1/L2/L3 对应测试补齐并可在 gate 中复现。
- A8：`make verify` + codegen + `make gate-release ENV=gamma` 全通过。
- A9：举报理由 → 提交 → 运营结案 → reporter 通知/进度回流无断点。
- A10：首页与沉浸态的负反馈归因、即时移除/跳过和后续窗口过滤语义一致。
