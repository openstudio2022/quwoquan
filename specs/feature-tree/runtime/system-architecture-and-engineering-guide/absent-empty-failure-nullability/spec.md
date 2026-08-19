# L3 Story：缺席、空值与失败的单义表达 (`absent-empty-failure-nullability`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为所有 Scenario 提供「结果状态不被伪装」的端云表达基线
>
> 设计归属：[L2 DEC-025](../design.md#dec-025)

## 1. 用户价值

作为跨端云消费同一业务对象的开发者，我希望任何返回值都能从类型和契约上区分「有值」「值为空」「没有这个值」「没做成」，从而不必对每个结果做防御性判空，也不会把一次失败当成一条空数据继续往下游写。

## 2. 范围与非目标

### In Scope

- 端云统一的四态语义：在场有值、在场为空、缺席、失败。
- 字段可空性由对象契约唯一 authoring，全部 codegen 管线派生同一运行时语义。
- Dart、Go、Python 与 JSON wire 各自的落地判据与禁止形态。
- 失败路径的结构化表达：`RuntimeFailure`、`AppError`、领域 sealed 结果或异常。

### Out of Scope

- 禁止可空类型本身；`T?`、`*T` 与省略键是合法的缺席表达。
- 改变既有业务字段的业务含义、operation 语义或错误码取值。
- 引入 `Result` / `Either` / `Optional` 第三方库或第二套错误模型。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 四态互不代偿

- 任何返回值必须落在且只落在「在场有值」「在场为空」「缺席」「失败」之一。
- 失败不得编码为缺席或空值；调用方不得依赖判空来发现失败。
- 缺席不得塌陷为空字符串或零值；空字符串与空列表是在场的业务值。
- 「结果未达成」判定为失败；「达成但无内容」判定为在场为空或缺席。

<a id="req-002"></a>
### REQ-002 可空性由契约唯一 authoring，跨管线单义

- 字段可空性只由对象契约声明：`fields.yaml` 的 `NOT_NULL` / `NULLABLE`、投影 `nullable`，或 wire schema 的 `required` / `default`。
- 声明为必填的字段在缺失时必须解码失败，不得由生成代码补默认值伪造成功。
- 生成代码不得补入契约未声明的默认值；每一处解码期补值都必须能追溯到契约上的显式 `default`。
- 生成器不得对未声明可空性的字段自行推定可空，未声明字段由门禁报告并按存量棘轮收敛。

<a id="req-003"></a>
### REQ-003 wire 上的空集合与零值稳定可见

- 非可空列表在 JSON 上必须序列化为数组，不得为 `null`，也不得因空而消失。
- 布尔字段不得因取值为 `false` 而从 JSON 中省略。
- 缺席优先以省略键表达；可空标量上 JSON `null` 与省略键等价。
- 「出站」按数据流判定：从出站序列化调用点回溯实参类型定位 struct 定义处，再沿字段类型递归展开。目录名不参与判定。
- 值类型 `bool` 带 `omitempty` 一律违反本条，与契约声明的可空性无关：`bool` 只有 true/false 两态，`omitempty` 让在场的 `false` 在 wire 上表现为缺席，而缺席是另一个状态。`NULLABLE` 允许该字段缺席，但不允许把在场的 `false` 说成缺席；确需三态用 `*bool`——nil 省略、`&false` 输出 `false`，指针在这一处恰好把三态表达对了。
- 「违反本条」与「造成用户可见故障」是两件事，修与不修的判断不同。`comment` / `content_reaction` 的 `replayed` 契约声明 `NOT_NULL`，端侧生成 fail-closed 校验，键消失即线上解码失败，属于缺陷。`media_asset` 的 `videoFastStart` 同样是 `bool` + `omitempty`，但契约为 `NULLABLE`、端侧全仓无引用、其中 `MediaAssetDeliveryReferenceSlice` 那处 handler 经 `mediaAssetHTTPResponseFromSlice` 转换后根本不输出该 struct，因此不构成故障。两者都要改：删掉 `omitempty` 只是让键重新出现，可空解码照样接受 `false`，没有兼容面，不值得为「不是故障」单独立项挂账。

<a id="req-004"></a>
### REQ-004 失败以结构化形态向上传递

- Dart 捕获异常后不得以 `null` 充当结果而不留证据；必须重抛、转为 `RuntimeFailure`、返回显式领域结果，或在确属降级时保留 `null` 并上报观测。异常处理点包含 `catch {}`、`catchError(...)` 与 `onError:` 三种形态。
- 空集合、`0` 与空字符串与 `null` 同受本条约束：把加载失败伪装成「列表是空的」，界面会显示「暂无内容」而不是「加载失败，请重试」。换一个零值不改变失败被压成在场为空这件事。
- 异常本身即形状判定（「这段输入不是一个 X」）的解析器，以 `try` 前缀命名承诺该语义，其 `null` 返回属于缺席而非失败。该命名只赦免 `null`，不赦免空集合——返回空 map 会把「不是 map」与「是个空 map」重新压回同一个值。
- `return false` 不在本条范围内：`false` 表达的正是「这次没做成」，调用方不会把它读成成功；异常被吞掉这件事由吞错预算门禁承担，两道门重叠只会让同一段代码得到两个结论。
- Go 失败必须经 error 返回；领域端口的未命中必须以 sentinel 或 `AppError` 表达，不得以空返回值兼作未命中信号。
- Go 指针只用于持久化层的可空列与需要三态的写入面，不得用于表达读模型的可选标量。
- Python 的 `None` 只表示未命中；取到值后的校验失败必须抛出。
- 降级可达成的路径必须返回可用的替代值并上报观测，不得以空结果静默降级。

## 4. 契约引用

- canonical：`quwoquan_service/services/*/contracts/**/fields.yaml`
- canonical：`quwoquan_service/contracts/metadata/_schemas/fields.schema.json`
- runtime error：`quwoquan_service/contracts/runtime_errors/**`
- codegen 语义锁定：`quwoquan_service/tools/codegen_app_metadata/nullability_single_semantics__local_contract_test.go`（经 `make -C quwoquan_service verify-nullability-single-semantics` 进入 service gate）
- app gate：`quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py`
- service gate：`quwoquan_service/scripts/verify/structure/verify_nil_semantics.py`
- 门禁自证：`quwoquan_ops/tests/local_contract/gate/test_nil_semantics__gate__local_contract_test.py`、`test_null_failure_isolation__gate__local_contract_test.py`、`test_ratchet_baseline_governance__local_contract_test.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 同一契约声明在所有管线得到同一语义

- GIVEN 一个字段在对象契约中声明为 `NOT_NULL`，另一个声明为 `NULLABLE`。
- WHEN 各 codegen 管线为该对象生成端侧模型与解码器。
- THEN 必填字段在缺失时解码失败，可缺字段在端侧保留缺席态。
- AND 不存在由生成器补入的空字符串或零值默认。

<a id="gwt-002"></a>
### GWT-002 失败不产生空引用结果

- GIVEN 一次会失败的端侧加工（如提交前的图片编码）。
- WHEN 调用方消费该加工的返回值。
- THEN 返回类型不以可空表达失败，失败只能经抛出到达调用方。

<a id="gwt-003"></a>
### GWT-003 空集合与 false 在 wire 上稳定出现

- GIVEN 一个响应包含空列表字段与取值为 `false` 的布尔字段。
- WHEN 服务端序列化该响应。
- THEN 列表字段在响应体原文中是 `[]`，不是 `null`，也不是缺键。
- AND 布尔字段的键存在且取值为 `false`。

<a id="gwt-004"></a>
### GWT-004 失败不塌陷为缺席，且留下证据

- GIVEN 一次已经取到值但随后校验失败的加工，或一次后台投递失败。
- WHEN 调用方消费其返回值。
- THEN 失败经抛出、error 或显式失败态到达调用方，不塌陷为 `None`、`nil` 或空集合。
- AND 该失败在运行期留下可观测证据，且不使所在处理链永久停摆。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的 metadata 单轨与 codegen 边界。
- 上游事实：对象契约的字段可空性声明与 runtime error 契约。
- 下游结果：端侧类型、解码器、wire 形态与门禁结论。
- 父级设计：`DEC-025`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 存量隐式可空字段、端口空返回与出站列表 omitempty

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍有三笔存量由同一份身份指纹棘轮承载并保持只减不增。其一，6 个字段的可空性没有显式 `NOT_NULL` 或 `NULLABLE` 声明，必须先由 `api_integration` 证明云侧下发语义。其二，`application`、`domain`、`adapters` 三层有 90 处二元 `return nil, nil` 兼作未命中信号。其三，19 处出站列表带 `omitempty`，必须连同构造期空列表归一化逐个裁决，避免删除标签后把 nil 切片序列化成 `null`。
- 完成判定：三笔计数归零后删除棘轮基线，`GWT-001` 可在不区分管线的前提下对全部字段成立，门禁转为无 allowlist 硬 BLOCK。

<a id="open-002"></a>
### OPEN-002 Python 脚本树的 `except` → `None`

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍有 101 处脚本在 `except` 块内直接 `return None`。其中一部分是校验失败伪装成未命中，需要改抛或留下结构化证据；其余是配置项或可选文件缺失，`None` 是准确表达。逐处裁决前不能用统一规则把合法缺席与失败一起判黑。
- 完成判定：逐处标注为「未命中」或「失败」，失败者改为抛出或返回显式失败态使 `GWT-004` 在脚本树上成立，此后由门禁按 Dart 侧同构判据硬 BLOCK。

<a id="open-003"></a>
### OPEN-003 wire 字段可空性存在三套并行 authoring

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍有同一字段的可空性由三处独立声明。`fields.yaml` 使用 `NOT_NULL` / `NULLABLE`，assistant wire 使用 `schema.yaml` 的 `required` / `default`，rtc payload 使用 `events.yaml` 的 `payload_fields` 与 `client_payload_defaults`。多条管线可能得到不同语义，必须收敛到单一 authoring。
- RTC 当前契约事实：
  - 生成器读错了实体。`rtc_signal_payload_codegen.go` 用 `ff.Entities["CallSession"]` 的字段定义决定端侧可空性，而真正上 wire 的载荷契约是 `CallEventPayload`；`events.yaml` 的 `payload_fields` 只提供键名列表。所以端侧类型的可空性来自聚合根，不来自载荷契约。
  - 服务端有两道过滤先后作用。`call_orchestrator_events.go` 先按 `payload_fields` 白名单挑键，Go 侧 `CallEventPayload` 的 `omitempty` 再让空值键消失。契约声明为 `NOT_NULL` 的 8 个字段中，`eventId` / `callType` / `initiatorId` / `maxParticipants` 四个在 Go 侧带 `omitempty`。
  - Runtime envelope 的键集合来自与端侧订阅同一路径的 Redis pubsub。`call.initiated`、`call.answered`、`participant.joined`、`participant.left` 与 `call.ended` 各自只携带 `payload_fields` 选中的键，`call.ringing` 只追加 durable stream。
  - 结论：契约声明 `NOT_NULL` 的 `status` 与 `eventId` 在上述全部事件上都不出现，`createdAt` 只在 `call.initiated` 出现。把生成物切成 fail-closed 必填会让来电与通话信令全面解析失败。这不是「服务端漏发」——`payload_fields` 本就只挑一部分字段下发，冲突的根源是可空性声明与下发白名单出自两份互不知晓的 authoring。
  - 证据：`quwoquan_service/services/rtc-service/tests/api_integration/rtc/call_session/realtime_payload_nullability_evidence__api_integration_test.go`。它只记录实发键并断言 `callId` 必发，刻意不断言「`NOT_NULL` 必发」——那正是本 OPEN 待裁决的事情。
- 收敛前置条件：先逐字段裁决该字段在每个事件上是否真的允许缺席，再作为一次同源变更同时落地「codegen 改读 `CallEventPayload`」「服务端去掉不该有的 `omitempty`」「端侧移除 `??` 兜底」。三者分开做任意一步都会打断来电信令。
- 完成判定：wire 字段的可空性与默认值收敛到单一 authoring，`REQ-002` 对全部管线成立，且 `GWT-001` 可以用同一份声明覆盖所有管线而不必分管线断言。

<a id="open-004"></a>
### OPEN-004 RTC signal delivery relay 的失败静默退出

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍存在 `CallSignalDeliveryCoordinator.Run` 在 `Deliver` 返回错误后直接退出、装配方以 `_ =` 丢弃返回值的风险。worker 可能静默停止后续通话信令投递，必须由日志、指标、重启与告警形成可观察恢复链。
- 完成判定：`GWT-004` 在该 worker 上成立——`Run` 的失败经日志与指标可见，装配处不得以 `_ =` 丢弃，投递中断有告警，并有测试证明单条事件失败不会让整条投递链永久停摆。
