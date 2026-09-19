# L3 Story：统一条目游标 (`unified-items-cursor`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览内容流的用户，
我希望连续翻页和刷新时保持统一条目顺序、稳定游标与账号隔离，
从而不会看到重复、遗漏或跨账号内容。

## 2. 范围与非目标

### In Scope

- “统一条目游标”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 统一条目游标

- feed 查询快照必须遵守 [`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)，并只从 content-service canonical Post/cursor contract 派生，不维护对象策略台账。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。
- feed 查询快照必须遵守 [`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)，并只从 content-service canonical Post/cursor contract 派生，不维护对象策略台账。
- feed item 对应的 post/user/media 数据必须进入对象缓存，query snapshot 不复制对象本体。
- 用户清理离线内容或浏览记录时可删除 query snapshot，但不得删除仍被收藏、关注、最近会话引用的对象本体。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 有效能力绑定窗口与有界补页

- App 必须发送生成能力；服务仅对整份声明缺席使用 canonical 契约显式固定的最小集合，非法声明或伪造摘要不得取得默认能力。
- 服务校验规范化能力摘要后才能建立窗口或读取续页；窗口、交付缓存及 App 查询快照均隔离不同摘要，能力变化须按 canonical 恢复动作重新发起首刷，不消费原摘要的 cursor。
- 在扫描/时间等 canonical 预算内过滤不支持项，候选足够时补满；候选确实耗尽与预算先耗尽可区分，不以无界扫描换取满页，也不以空结果隐藏预算失败。
- 实体主页与 Post 保持同一有序序列；续页、重试与回翻不能重复交付或重排已交付页。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- canonical：`quwoquan_service/contracts/metadata/_shared/types.yaml#ClientContentPresentationContract`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/feed_delivery_page/fields.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/ranked_recommendation_window/fields.yaml`
- 能力及固定最小集合约束：[`content-type-framework REQ-006`](../../content-type-framework/spec.md#req-006)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 统一条目游标

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“统一条目游标”对应的公开行为。
- THEN feed 查询快照遵守 [`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)，只恢复从首屏 cursor 连续可达的完整页且不维护对象策略台账。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 缺声明、非法声明与跨语言摘要一致

- GIVEN canonical 契约声明可真实支持的固定最小集合与摘要规则，正常 App 由同源生成器产生能力；请求分别为整份缺席、合法声明、结构非法、集合无效、摘要缺失和摘要不匹配。
- WHEN 服务处理首刷请求，Go、Python 与 Dart 对相同合法能力样本生成规范化字节和摘要。
- THEN 只有整份声明缺席使用固定最小集合，其有效摘要与显式发送该集合一致；新增枚举成员不会自动扩大默认能力，返回项均在该集合内。
- AND 正常 App 发出的声明与其生成支持能力一致，服务重算摘要后接受；三种语言对同一集合及契约允许的等价输入给出相同规范化字节和摘要，对不等价集合不得误认同一能力身份。
- AND 结构非法、集合无效、摘要缺失或摘要不匹配均返回 canonical typed 拒绝，不创建成功窗口、不读取默认窗口、不按无声明处理；空集合是否有效只由 canonical 校验规则裁定。

<a id="gwt-003"></a>
### GWT-003 过滤补页、两类耗尽与摘要隔离

- GIVEN 同一候选源混有支持和不支持项以及独立实体主页，分别可在预算内补满、在预算内扫描至真实末尾、在扫描至末尾前耗尽预算；客户端另持有能力摘要 A 的 cursor 与已交付页。
- WHEN 服务生成或续接页面，客户端用同一摘要重试/回翻，并尝试以不同有效摘要 B 续接 A 的 cursor。
- THEN 预算内支持候选足够时按请求页大小交付同一序列，不支持项不下发，实体主页与 Post 共享序位且不产生 sidecar。
- AND 候选确实耗尽时可交付不足一页或空页并明确无后续 cursor；页大小不大于请求值，已交付项不重复。
- AND 预算先耗尽时停止扫描并返回可区分于候选耗尽的 canonical typed 终态；不得声称已无内容或返回虚假完成 cursor，已显示页仍可浏览，恢复动作及是否保留部分页只按 canonical 契约执行。
- AND 摘要 B 不能读取 A 的窗口、交付缓存或 App 查询快照，也不能续接 A 的 cursor；响应采用 canonical 不匹配终态，恢复后以 B 从新首刷开始，不静默替换窗口继续旧页。
- AND 摘要 A 的有效重试与回翻保持已交付序位、页边界和对象身份，补位不改写已交付历史页，不重复创建交付事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 统一条目游标 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“统一条目游标”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 能力声明与过滤分页边界缺少贯通证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：固定最小集合、声明验证、跨语言摘要一致、两类耗尽和不同摘要 cursor 隔离尚缺真实端云证明，无法保证扩展后安全续页。
- 完成判定：`GWT-002`、`GWT-003` 每个结果子句由真实 local_contract/API 测试直接绑定；App 请求与查询快照隔离另有真实客户端测试，所有证据匹配同一候选。
- 依赖：canonical 契约固定最小集合的成员和生成来源、规范化规则、预算耗尽的部分页/cursor/恢复语义及不匹配错误；这些规则未声明前保持阻断，不由测试或客户端自行发明默认。
