# L3 Story：个性化排序 (`personalized-ranking`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望端侧不得解析 token，仅做透传和存储，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “个性化排序”的输入、可观察主路径、失败语义以及与父能力的交接。
- sort=recommend 首屏与翻页路径。
- cursor 透传、不解析、连续推进。
- 强反馈过滤未来窗口，弱反馈影响未来重排。
- 端侧已看窗口回滚稳定。
- 协同召回、排序校准、时间衰减与上下文化排序的商用成熟度规格。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 个性化排序

- “个性化排序”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 端侧不得解析 token，仅做透传和存储

- 端侧不得解析 token，仅做透传和存储。

<a id="req-003"></a>
### REQ-003 排序策略、特征与解释一致

- policy.yaml、feature_registry、ContentCandidate、RuleScorer 和 App 解释显示均对齐。

<a id="req-004"></a>
### REQ-004 契约与字段策略必须与 metadata 保持一致

- 契约与字段策略必须与 metadata 保持一致。
- 本 Story 禁止新增 intersection-only ranker，也不把 `/score` 同步塞进 feed 读路径。
- `affinityIntersectionScore` 没有 `intersectionConfidenceLabel` 时不得参与候选级融合。

<a id="req-005"></a>
### REQ-005 请求期设备/视口/时段/粗地域 soft boost

- 推荐请求可携带低基数 `viewportProfile` 与 `deviceClass`，并结合服务端权威时间桶、既有用户画像以及用户已同意提供的粗粒度 region 形成 bounded soft boost。不得为推荐主动弹定位权限，不得采集或传输精确位置；region 缺失必须退化为无地域 boost，而非失败。
- 横屏偏好仅提高原始 `width/height` 判定为横向的 image/video 候选，不过滤竖向媒体、文章或其他内容。所有 boost 均有上下界并保留基础排序与多样性，不得成为 hard filter。
- 首版在现役 ranker 输出后执行可解释后处理，不修改模型训练、训练特征或模型版本；服务端时间桶而非客户端时钟参与计算。
- 请求开始时冻结 viewport/device/time-bucket/region/profile 与 policy identity，并将其绑定进不可变 RankedFeedWindow/cursor/cache identity。窗口形成后旋转、横屏或设备窗口变化不得重排旧窗；只有新首刷/刷新可使用新上下文。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 个性化排序

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“个性化排序”对应的公开行为。
- THEN 通过父能力公开契约交付“个性化排序”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 请求期 soft boost 有界且窗口稳定

- GIVEN 候选同时含横/竖 image/video 与其他内容，用户可能具有画像、已同意粗 region，客户端声明 viewportProfile/deviceClass。
- WHEN 服务端在新首刷生成最终排序窗口，随后客户端旋转、进入横屏并继续翻页。
- THEN ranker 后处理只施加有界 soft boost；横屏只提升横向 image/video 且不删除其他候选，未同意或缺少 region 时不弹权限、不传精确位置并按无地域 boost 继续。
- AND 服务端时间桶、画像、粗 region、viewport/device 与 policy 在请求期冻结并进入 window/cursor/cache 身份；已形成窗口及续页顺序不因旋转重排，刷新后才可使用新上下文。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 请求期上下文 soft boost 与窗口稳定证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`GWT-002` 已冻结 viewport/device、服务端时间桶、画像与已同意粗 region 的 bounded soft boost，但尚缺逐子句 current `spec_ref`；不得以策略配置存在、离线排序样例或客户端旋转截图宣称闭合。
- 完成判定：`GWT-002.t1..t5` 由 local_contract 与 api_integration 直接绑定，覆盖候选全集不变、横向 image/video 仅 soft boost、无权限弹窗/无精确位置、训练输入不变、window/cursor/cache 身份冻结、旋转后旧窗稳定与刷新后新上下文生效。
