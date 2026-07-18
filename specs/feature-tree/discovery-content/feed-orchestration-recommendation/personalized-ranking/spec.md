# L3 特性：personalized-ranking

## 功能说明
- 建立发现流的个性化排序基线：`sort=recommend` 与 cursor 分页并存。
- 固化端云协同边界：
  - 端侧维护已看窗口（记录内容回滚不变化）。
  - 云侧仅计算未来窗口（cursor 之后）并应用实时反馈。
- cursor 使用 opaque token（端侧透传，不解析内部结构）。

## 范围
- 云侧：
  - `GET /content/feed` 支持 `sort` 查询参数。
  - 推荐引擎支持基于 token 的 future offset 分页。
  - 强反馈即时过滤未来窗口；弱反馈影响未来重排权重。
- 端侧：
  - Feed 请求透传 `sort` 与 `cursor`。
  - 维持已看窗口队列，滚动回看优先使用本地记录队列。

## 非目标
- 不在云侧维护长记录窗口队列（记录队列由端侧维护）。
- 不引入新的业务对象，仅在现有 Post/Feed 契约上扩展。
- 本 Story 不直接拥有曝光记忆、动态预算或生命周期复活；这些归属 `discovery-content/exposure-governance`。
- 深度排序模型平台轨不进入当前商用成熟度门槛。

## 商用成熟度候选规格

当前 `sort=recommend` 基线已完成强反馈未来窗口抑制。为达到非深度商用成熟度，后续排序成熟度必须补齐三个 L3：

- `collaborative-recall`：itemCF/swing i2i 与 u2i 非深度协同召回，读路径只消费离线物化候选。
- `ranking-calibration`：规则分、模型分、内容质量分与交集信号的校准口径，支撑混排、阈值和动态曝光预算。
- `time-decay-contextual-ranking`：统计量时间加权衰减与 requestHour/weekday/season/eventWindow 上下文排序。

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
- A6：协同召回、排序校准、时间衰减与上下文化排序的规格已登记，且不与 `exposure-governance` 或深度模型平台轨混淆。
- A7：metadata/codegen/gate 一致性校验通过。
- A8：端云自动化测试映射完整（contract + provider/journey）。
