# L3 Story：合集查询窄身份委托 (`collection-query-delegation`)

> 所属能力：[设置、设备与账号安全](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为已登录用户，我希望网关读取合集时只代表我的当前有效身份访问授权范围内的数据，身份撤权后不能借旧委托读取私有内容。

## 2. 范围与非目标

### In Scope

- UserAccount authority 独立核验原始用户凭据与当前 Persona 归属后签发窄合集查询委托。
- content owner 每次读取前在线验证委托绑定与当前身份状态，再执行自己的资源权限判断。

### Out of Scope

- 不授予网关签发密钥，不扩展 Assistant 或 command 委托，不承诺单会话 logout 即时撤销在途 grant。
- 不生成、注入或轮换真实密钥，不声明环境或发布资格。

## 3. 行为要求

### REQ-001 权威签发不接受调用方自报身份

- 仅受信 API Edge 可申请；authority 独立验证源 access credential 及当前 account-persona 归属、存续、状态和 epoch。
- 委托只服务两个 canonical 合集读取操作，限制为一个真实请求；网关不能更改身份、目标、hash、方法路径、摘要或 surface。
- TTL 为六十秒且不超过源凭据剩余有效期，不允许客户端延长。

### REQ-002 每次重验且不失败降级

- 仅受信 content-service 可在线验证；actual caller 与委托 recipient/delegate 不匹配时拒绝。
- authority 每次验证重读当前账号与分身事实，撤权、过期、错绑定、未知操作和依赖故障不产生 verified identity，不回退匿名。
- 合法同请求重试不改变权限或到期时间；既有 Assistant 与 command 安全边界不变。

## 4. 契约引用

- [UserAccount operations](../../../../../quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml)
- [UserAccount fields](../../../../../quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml)
- [UserAccount privacy](../../../../../quwoquan_service/services/user-service/contracts/account/user_account/privacy.yaml)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 源身份核验和窄请求绑定

- GIVEN 源 access credential 与当前账号分身关系有效，API Edge 持有合法申请权限。
- WHEN authority 签发且 content owner 在线验证同一合集请求。
- THEN 只得到源凭据对应的当前身份，grant 不超过六十秒或源剩余有效期，重复同请求不延长到期。
- AND 跨账号分身、伪造源凭据、假 service、错 recipient/operation/resource/hash/digest/method/path/surface 均在资源读取前拒绝。

<a id="gwt-002"></a>
### GWT-002 撤权与依赖失败不放行

- GIVEN grant 曾经合法且尚在有效期内。
- WHEN 账号关闭、封禁、epoch 改变、分身退役或归属变化，或者 authority 上游不可用。
- THEN 每次验证均拒绝并不产生 verified identity，不能使用缓存成功或匿名回退。

## 6. 依赖

- 身份 L1 DEC-002、settings DEC-003；UserAccount 与 Persona 公开读取边界；content owner 实际资源鉴权。

## 7. 开放事项

### OPEN-001 窄查询委托真实运行与端云装配未闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：authority 签发、在线验证及 UserAccount/Persona 权威读取已经具备独立内部实现；仍缺 API Edge 源凭据转交、content 实际 caller 与 grant act 独立核验、两条合集 persisted query 实际执行联程，以及轮换旧材料保留/紧急撤销与环境加载的完整运行依据。仅 authority HTTP/PostgreSQL 联程不代表跨服务委托可用，真实材料未配置时生产装配必须拒绝。
- 完成判定：`GWT-001`、`GWT-002` 由真实签发验证 local_contract/api_integration 直接绑定，源凭据、当前身份、超时与无私有读取负例通过。
- 依赖：canonical authority 合同、正式组合、受保护内部 conformance；环境/App/UAT/release 仍独立准入。
