# L2 特性：assistant-runtime-foundation

## 功能说明

- 承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- 为 `run-stream-policy`（运行协议）与 `learning-event-feedback-injection`（学习回路）提供对象状态真相源；会话内 @小趣 与个人助手全屏会话共享同一 runtime，不维护第二套助手逻辑。

## 约束

- conversation/turn 状态必须持久化于对象专属 Store（MongoDB `assistant_conversations`/`assistant_runs`），服务重启后 run 可读、SSE resume 语义明确；禁止进程内 map 承载业务状态。
- 命令按写入形态裁剪：创建会话/轮次/订阅为一次创建（稳定 intent + 唯一约束 + receipt）；订阅状态、consent grant/revoke 为命名状态迁移（服务端内部 CAS + no-op receipt）；公开请求不携带调用方版本字段。
- cron/主动投递的领取必须用带 TTL 的 lease（`acquireDueLeases` 语义），禁止内存 claim；多实例可安全并发。
- `SkillConsent` 是敏感能力（如 `personal_content_access`）的唯一授权真相源：执行点强制校验、失败关闭、按 account/persona 隔离、状态变更产生可审计事件；任何"store 未装配即放行"或"查询失败视为未启用"的静默分支都是缺陷。
- 端侧只经对象级 typed Facet 消费；不可用状态以结构化 `RuntimeFailure` 呈现，禁止本地合成成功数据或假兜底。

## 验收标准

- A1：会话创建、轮次运行、订阅管理、consent 授权在真实存储上闭环，重启不丢状态。
- A3：consent 负例（未授权、撤权后、伪造身份、store 不可用）全部 fail-closed。
- A7：25 个 operation 的 reliability/telemetry/slo/commercial 合同与 metadata 一致。
- A8：local_contract / api_integration / user_acceptance 三层证据可复跑。
