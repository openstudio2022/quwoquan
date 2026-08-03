# L2 Design：用户 Skill 产品与集成平台 (`skill-product-integration-platform`)

> 对应规格：[L2 spec](./spec.md)
>
> 设计触发原因：四个 Story 共享 package active pointer、账号/共享 surface 权限、Context provenance、Connector grant 与 Run digest 生命周期。

## 1. 背景、目标与非目标

- 背景：已有 Skill Catalog/Consent/Subscription/Package/Context，但生产仍扫描文件资产，用户端只呈现分类和开关，启用与主动投递混为一体。
- 设计目标：以 immutable active package 和四个独立用户/共享对象建立单轨，使普通 Skill 资产化扩展并在个人、群聊、圈子安全运行。
- 非目标：开放第三方代码、复制业务数据、由 Assistant 保存 OAuth 凭证或让 App 成为权限真相源。

## 2. Story 协作与状态流

- 状态 owner：SkillPackageRelease/Catalog/UserSetting/Consent/Subscription/SurfacePlacement 属 Assistant；Connector connection/invocation 属 Integration。
- 并发边界：package active pointer、Setting/Placement revision 用 CAS，Run 冻结 digest，Consent/Connector 每个安全边界重新求交。
- 幂等边界：stage/activate/rollback、setting save、subscription trigger/delivery、placement change 与 connector invocation 均有幂等 receipt。
- 一致性窗口：active pointer 与新 Run 强绑定；Chat/Circle placement 和 Connector status 最终一致，失效时 fail-closed。

## 3. 端云与数据流

- App 责任：渲染 package CatalogProfile/InputProfile/Presentation，收集确认，执行 native continuation；不扫描资产或持有凭证。
- Metadata/contract：Assistant 对象 contracts 拥有 package/setting/consent/subscription/placement/run wire；Integration contracts 拥有 connector wire。
- Service/Data/Ops 责任：publisher 构建签名 package，Assistant active resolver、Reader Registry 和 Tool Router 只消费冻结资产，Integration Gateway 隔离 Provider。
- 缓存或投影：Catalog detail 与活动列表可缓存/投影，digest mismatch 必须失效；Context/Tool 大结果进 Artifact Store。
- 外部依赖：Domain Reader、Public Web Runtime、Connector Gateway、device continuation 与 model provider。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 Package 冻结能力、动态授权在安全边界求交

- 决策：Run 冻结 package digest、schema 和允许能力上限；Setting、Consent、Surface policy、Connector grant 与 runtime availability 不冻结，在每个安全边界重算交集。
- 理由：冻结全部授权会让撤权失效，完全动态读取 package 又会使长任务恢复不可重放。
- 被否决方案：Run 启动时永久缓存 consent/token、运行时扫描最新 Manifest、把 Subscription 当 enable、由 App 决定工具集合。
- 影响 Story：[`active-skill-package-catalog`](./active-skill-package-catalog/spec.md)、[`skill-user-lifecycle`](./skill-user-lifecycle/spec.md)、[`shared-surface-skill-placement`](./shared-surface-skill-placement/spec.md)、[`domain-reader-connector-grant`](./domain-reader-connector-grant/spec.md)
- 关联要求：`REQ-001`、`REQ-002`、`REQ-003`
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败：package 不存在/签名或 digest 错误、schema 不兼容、权限撤销、Reader/Connector 不可用、共享可见性冲突。
- 检测：active pointer CAS、digest/schema validator、policy intersection、capability readiness 和 audit hook。
- 可见结果：禁用/需授权/连接失效/能力暂不可用/旧客户端降级，不伪装成功。
- 恢复：激活 last-good package、刷新授权或连接、从 checkpoint 在新安全边界续接。
- 禁止 fallback：本地 Manifest、内置 catalog、旧 credential、个人记忆进入共享 surface、Skill 专用分支。

## 6. 质量与观测

- 指标覆盖 catalog→首次成功转化、设置/授权流失、package activate/rollback、Skill D7/D30、主动退订、placement 禁用、Reader/Tool/Connector 成功率、隐私拒绝和模板降级。
- package、模板和 replay 以 digest 内容寻址；运行 trace 只保存 capability/connection reference，不保存 secret、token 或第三方原始响应正文。
- 新节点或能力的 rollout 必须先证明最低支持 App 的 node/capability coverage；未知内容使用 fallbackMarkdown/plain text。
