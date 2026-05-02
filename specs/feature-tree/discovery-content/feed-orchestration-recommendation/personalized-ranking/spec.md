# L3 特性：personalized-ranking

## 功能说明
- 建立发现流的个性化排序基线：`sort=recommend` 与 cursor 分页并存。
- 固化端云协同边界：
  - 端侧维护已看窗口（记录内容回滚不变化）。
  - 云侧仅计算未来窗口（cursor 之后）并应用实时反馈。
- cursor 使用 opaque token（端侧透传，不解析内部结构）。

## 范围
- 云侧：
  - `GET /v1/content/feed` 支持 `sort` 查询参数。
  - 推荐引擎支持基于 token 的 future offset 分页。
  - 强反馈即时过滤未来窗口；弱反馈影响未来重排权重。
- 端侧：
  - Feed 请求透传 `sort` 与 `cursor`。
  - 维持已看窗口队列，滚动回看优先使用本地记录队列。

## 非目标
- 不在云侧维护长记录窗口队列（记录队列由端侧维护）。
- 不引入新的业务对象，仅在现有 Post/Feed 契约上扩展。

## 约束
- metadata-first：先更新 `service.yaml` 与测试契约，再 codegen。
- cursor token 需要版本字段，保证后续协议演进兼容。
- 端侧不得解析 token，仅做透传和存储。

## 验收标准
- A1：`sort=recommend` 首屏与翻页路径可执行，返回稳定。
- A2：同一会话下，cursor 跨页无重复，`nextCursor` 可连续推进。
- A3：用户回滚已看内容时，端侧记录窗口不抖动。
- A4：强反馈（dislike/report/block）仅影响未来窗口，不回写记录窗口。
- A5：弱反馈（click/like/favorite/dwell）可影响未来排序，不破坏分页连续性。
- A7：metadata/codegen/gate 一致性校验通过。
- A8：端云自动化测试映射完整（contract + provider/journey）。
