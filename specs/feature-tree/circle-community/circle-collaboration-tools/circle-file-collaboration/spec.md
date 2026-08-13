# L3 Story：圈子资料协作 (`circle-file-collaboration`)

> 所属能力：[`circle-collaboration-tools`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为圈子成员或运营者，我希望在圈子内以明确层级浏览、新建、重命名和删除资料，且只看到自己有权访问的 typed 元数据，从而在不暴露存储身份或绕过 MediaAsset owner 的前提下完成协作。

## 2. 范围与非目标

### In Scope

- `ListCircleFiles` 与 `GetCircleFile` 的 typed reader、稳定分页、BOLA 和脱敏。
- `CreateCircleFile`、`UpdateCircleFile` 与 `DeleteCircleFile` 的 owner 权限、version、幂等 receipt 与无部分副作用。

### Out of Scope

- MediaAsset 上传、处理、公开分发与存储 object key。
- CircleGroup 到 Chat Conversation 的 binding、成员投影、Inbox、realtime、reclaim 与 DLQ 终态。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 CircleFile 只由 Circle owner contract 读写

- 客户端只调用 `circle.circle_file` generated operations，不传递 Persona 别名、存储 key、upload URL 或绕过 Circle/MediaAsset owner 的字段。
- reader 返回 `CircleFilePageSlice` 或 `CircleFileSlice`；command 返回 `CircleFileCommandResult`，禁止以聚合存储模型或单项 slice 冒充分页响应。

<a id="req-002"></a>
### REQ-002 CircleFile 变更保持 version、幂等与 MediaAsset owner 边界

- 创建文件必须引用已 ready 且归属调用主体的 MediaAsset；创建文件夹不得携带 asset。
- 更新使用 owner version 做乐观并发控制；创建、更新和删除使用稳定幂等身份，冲突不得推进 state、receipt 或 outbox。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_file/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_file/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_file/errors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/object.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分页列出圈子资料

- GIVEN 调用 Persona 有权读取目标 Circle 及父文件夹，且至少存在一条可见资料。
- WHEN Persona 调用 canonical `ListCircleFiles` 并沿 owner cursor 继续分页。
- THEN 每页返回 nonempty typed `CircleFilePageSlice`，顺序、cursor、parent 筛选稳定且不重不漏。
- THEN 无权访问、非法 cursor 或 owner reader 失败返回 canonical typed failure，不泄露任何资料或合成成功空页。

<a id="gwt-002"></a>
### GWT-002 读取单个圈子资料

- GIVEN 调用 Persona 有权读取目标 CircleFile。
- WHEN Persona 调用 canonical `GetCircleFile`。
- THEN 返回 nonempty typed `CircleFileSlice`，identity、version、parent、type、asset 引用与 owner authoritative readback 一致，不含 storage identity、object key 或 upload URL。
- THEN 文件不存在、BOLA 或 owner reader 失败返回 canonical typed failure，不以空 slice 合成成功。

<a id="gwt-003"></a>
### GWT-003 创建圈子资料

- GIVEN 调用 Persona 对目标 Circle/父文件夹有写权限，文件名与类型合法；文件引用已 ready 且归属调用主体的 MediaAsset，文件夹不携带 asset。
- WHEN Persona 使用稳定幂等键调用 canonical `CreateCircleFile`。
- THEN command receipt 与 fresh `GetCircleFile` authoritative readback 收敛到同一 file identity、初始 version、parent、type 与 asset 引用，且只提交一次 state 与 outbox。
- THEN 同键同语义重放返回同一 file/receipt；BOLA、MediaAsset 未 ready/不归属、输入或幂等冲突返回 canonical typed failure，不产生部分 state、receipt 或 outbox。

<a id="gwt-004"></a>
### GWT-004 更新圈子资料

- GIVEN 调用 Persona 对目标 CircleFile 有写权限，并持有 owner 当前 version。
- WHEN Persona 使用稳定幂等键和 expected version 调用 canonical `UpdateCircleFile`。
- THEN command receipt 与 fresh `GetCircleFile` authoritative readback 收敛到同一 file 的新 name/parent 与 version，且只提交一次 state 与 outbox。
- THEN 同键同语义重放稳定；BOLA、stale version、循环 parent、输入或幂等冲突返回 canonical typed failure，不产生部分 state、receipt 或 outbox。

<a id="gwt-005"></a>
### GWT-005 删除圈子资料

- GIVEN 调用 Persona 对目标 CircleFile 有删除权限，且文件夹约束允许删除。
- WHEN Persona 使用稳定幂等键调用 canonical `DeleteCircleFile`。
- THEN command receipt 与 fresh owner readback 共同确认目标已不可读，且只提交一次 state 与 outbox；不删除或改写 MediaAsset 事实。
- THEN 同键同语义重放稳定；BOLA、非空文件夹、不存在或幂等冲突返回 canonical typed failure，不产生部分 state、receipt 或 outbox。

## 6. 依赖

- 前置要求：[`circle-collaboration-tools`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

（当前无开放事项：GWT-001..GWT-005 均已由真实 api_integration 测试子句级绑定。）
