# L3 Story：实体链接模板元数据（entity-link-templates-metadata） (`entity-link-templates-metadata`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为打开实体链接的用户，
我希望让分享链接、站内跳转和归因参数解析到同一类型化对象与目标页面，
从而稳定到达目标且保留合法来源上下文。

## 2. 范围与非目标

### In Scope

- “实体链接模板元数据（entity-link-templates-metadata）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 5 类实体（post/circle/user/entity_homepage，「我」等同 user）的 web/deeplink 双链与 navigation 映射。
- 对外引流归因参数 attribution_params 结构。
- 智能中转落地页 transfer_pages（short_link/universal_landing）结构。
- 跨 App 口令 share_token 结构。
- 端侧 codegen 工具改造与调用点替换（/dev 切片）。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 实体链接模板元数据（entity-link-templates-metadata）

- 出站链接必须注入受控归因参数，入站路由匹配前必须剥离归因参数且保留归因上下文。
- `link_templates.yaml` 每个 entity 的 `navigation.route_id` 与 `param_bindings` 必须能在 `app_routes.yaml` 解析；由 `verify_link_templates_route_ids.py` 在 `gate_repo.sh` 中 fail-closed 阻断合入。

<a id="req-002"></a>
### REQ-002 对外链接统一携带归因参数且入站被剥离

- 对外链接必须统一携带受控归因参数；解析目标路由时不得把这些参数当作业务主键。

<a id="req-003"></a>
### REQ-003 中转页与口令回溯到同一实体真相源

- 中转页与口令必须把四类实体目标解析到与直接链接相同的 canonical 实体身份。

<a id="req-004"></a>
### REQ-004 链接模板/归因/口令/中转页结构契约

- link_templates.yaml 的 entities/attribution_params/transfer_pages/share_token 结构合法且 route_id 可解析。

<a id="req-005"></a>
### REQ-005 显式映射：navigation.route_id 必须引用 app_routes.yaml 已有 id；param_bindings 声明链接参数 → 路由 path 参数

- **显式映射**：`navigation.route_id` **必须**引用 `app_routes.yaml` 已有 `id`；`param_bindings` 声明链接参数 → 路由 path 参数。
- 禁止在 Dart 维护第二套「外链 path → 页面」表；Universal Links / App Links 解析应 **回溯到同一 metadata 行**（实现落在后续 slice）。
- `route_id` 不在 `app_routes.yaml` 中存在的，**禁止**合入（CI/verify 或 codegen 阶段校验）。
- metadata **不得**写入生产环境具体域名（仅 `runtime_origin_binding` 声明 **键名** 与来源类型）。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 实体链接模板元数据（entity-link-templates-metadata）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“实体链接模板元数据（entity-link-templates-metadata）”对应的公开行为。
- THEN 路由打开原目标实体，业务参数不含归因键，归因上下文仍可用于事件记录。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 对外链接统一携带归因参数且入站被剥离

- GIVEN 系统为实体生成出站链接并随后接收该链接。
- WHEN 路由解析业务目标。
- THEN 受控归因参数被保留为上下文且从业务主键解析中剥离。

<a id="gwt-003"></a>
### GWT-003 中转页与口令回溯到同一实体真相源

- GIVEN 用户通过中转页或口令访问任一支持实体。
- WHEN 系统解析并恢复目标。
- THEN 解析结果与直接链接使用同一 canonical 实体身份。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 实体链接模板失败语义尚无直接证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001.t2` 的直接证据。t1 已由 `content_share_template_public_link__local_contract_test.dart` 断言（deeplink 不含归因键、landingUrl 保留 share_id/utm_source）并实跑通过，route_id 存在性也已由 `verify_link_templates_route_ids.py` 在 gate 中阻断，但失败语义未单独证明。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 对外链接统一携带归因参数且入站被剥离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：归因 query 解析单测覆盖注入与剥离两端。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 中转页与口令回溯到同一实体真相源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：中转页与口令解析单测覆盖 4 类实体目标。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 链接模板/归因/口令/中转页结构契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：link_templates.yaml 的 entities/attribution_params/transfer_pages/share_token 结构合法且 route_id 可解析。
- 完成判定：`GWT-001` 的路由解析、`GWT-002` 的归因参数注入剥离与 `GWT-003` 的中转页/口令同源解析对应行为满足——link_templates.yaml 的 entities/attribution_params/transfer_pages/share_token 结构合法且 route_id 可解析。
