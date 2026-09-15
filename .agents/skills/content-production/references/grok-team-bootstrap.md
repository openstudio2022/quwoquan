# Grok 团队初始化与刷新入口

本文件是初始化唯一入口。岗位只读 [team](team.md)，简介与现场清单只读 [grok-team-rebuild](grok-team-rebuild.md)，阶段命令只读 [pipeline](pipeline.md)。本轮只优化本机单账号，VM/跨账号扩容暂停。A/B/C 是三种操作场景，不是三套运行架构，最终同用四类岗位与整批流程。

## 共同硬门

四类岗位为创作总监、多创作者、独立多 QA、电脑管家；四载体创作方向不等于固定人数。按获准槽位核对群“马不停蹄创作群”，先用 name/title 与稳定 Bot ID 匹配复用；同名多对象、职责冲突或 ID 不可回查即 BLOCKED，不自动删除、隐藏、换 ID 或复制另一账号 UUID/凭证/sessionId/runId/任务授权。作者/QA实际并发受总预算和经验证的宿主能力限制，岗位简介不是技术隔离。

只有受支持 Bot/群工具和本次配置授权同时存在才更新/补缺，变更后重新读回实际 Bot/群 ID、成员与描述版本。无接口则输出逐岗精确人工清单及待读回字段，不宣称活跃 Bot 已生效；文件/简介修改、请求发出、Bot 自报与文档测试都不算宿主生效证据。创建工具缺失可报告 NEEDS_MANUAL_CREATION，已有对象无法更新则报告 BLOCKED 与人工更新步骤，不能把手工待办当完成。

初始化不生产、不认领、不启 Routine、不 publish/finalize、不 Git、不清理。模型不可核实写 modelCapability=unknown，不能宣称升档。核实际源码/Skill 摘要、活动 execution/workspace 根、coordination DB identity、QWQ_PUBLISH_ROOT/仓身份；外盘时核挂载卷 UUID 与 repositoryId=quwoquan-content，不把示例路径当事实，不回退内盘空池，不用旧外置副本判断运行状态。

### 共享信息与总监检查读回

A/B/C均逐角色核同一当前有效任务版本及生效范围，包含已授权动作、预算余量、任务占用、receipts、QA结果、publish proof、阻断与恢复裁定；全员可读，不共享凭证/无关隐私，写 scope 仍隔离。总监须有可读回的当前安排确认；无任务场景明确无有效生产授权，不从旧聊天继承。受影响角色无法读必要事实时暂停对应正式动作，不能仅凭“已学习”。

现场核总监是否具备真实原生通知/Routine/状态读取与单个非重入检查能力，启用须另有授权；约10分钟检查不是自动生效配置。只支持手动触发时明确人工唤醒及责任人，不承诺无人值守，不每 tick 新建总监/生产调用，不用 Cursor Automation 替代。缺 Grok 管理或 native 调用读取工具时保留 BLOCKED，人工清单必须包含该缺口和验证动作。

## 模式 A：新建或核对

> 读取本入口执行模式 A。只配置/核对四类岗位与获准槽位，匹配 Bot 复用，缺岗仅在受支持创建工具和授权均在场时补齐；不盲删空 Bot、不复制历史身份。读取 rebuild 简介与读回清单，核实际成员、工具/媒体链、native actor可回查性、活动根、手册版本、全角色共享事实与总监非重入检查支持。初始化不认领、不生产、不启 Routine、不清理。逐角色返回 reused/created/needs_manual_creation/conflict 和证据；最终仅 READY_READ_ONLY/NEEDS_MANUAL_CREATION/BLOCKED，不报 ACTIVE。

## 模式 B：已有且无任务重组

> 先用 coordination、execution receipts 与可信 native 状态证明无在飞/待接管任务；不能确认就转模式 C，不能写“无任务”。保留稳定 Bot ID、历史、review、handoff与作品，原位更新四类岗位、作者主会话/QA seal职责及总监唯一发布责任，不重建重复 Bot、不继承旧授权。按共同清单读回配置、工具、共享版本、活动根与总监检查触发能力。空载配置验收仅 READY_READ_ONLY，生产按另有原授权启动；工具不足输出精确人工清单，不报生效。

## 模式 C：已有且有任务或 unknown 安全重组

先填写当前任务/iteration 版本与原授权引用、deploymentId/团队 generation、既有 claim/handoff、允许动作闭集、剩余目标、候选/站点/费用/存储预算与 author/QA/退出预留、活动根和停止条件。不要为换规则创建另一 deployment 或把 C 当自动认领授权。

> 逐工作单元记录旧scope/actor/receipts/版本到现有 checkpoint，读回三份 seal、author resultRefs/草稿、QA 原件、publish proof、未完/未评/blocked/unknown 与前任 handoff。旧调用保持原身份/授权至安全交接点后才更新该角色；新任务采用同一新规则。不等待全队同步切换，不改旧 receipt，不强停、不并行重派、不追溯替换 actor 或旧授权。unknown 保留其 scope和证据，点名责任人与下一动作；仅冻结冲突正式写，其他安全已授权工作可继续。通过受支持入口更新并逐角色读回共享版本及实际配置，不能确认则保持 CLAIMED_BLOCKED/BLOCKED。不以“已改手册”报告 ACTIVE。

安全交接要求可信终态或获准隔离、原 actor/receipts、预算、唯一归属及 generation 写围栏均可核实。若需原契约 claim/release，沿既有 coordination 入口读回本 deployment 已持同 shard/generation；一队一 active shard，不抢占，响应丢失重放同幂等键，不造新归属。正常退出停止新增→drain/获准隔离→持久化并校验 handoff→owner/generation CAS release；旧代不能写入或释放新代。十分钟无报告、退出登录、inflight=0、TTL、预算未知或旧账号不响应均不构成释放依据。这是安全切换，不保留长期旧权限兼容层。

### 模式 C：现有独立 QA 未投入时的最小操作清单

按顺序核查，不将整队全部重建或“重读技能”当作切换：

1. 复用已有独立 QA 稳定 ID，核实际群成员、资料访问与当前只读/生产授权。QA 对象存在不等于已加入工作群、具备媒体链或可领取正式 review。
2. 经配置授权，通过受支持入口将其加入正确群并读回成员/职责、同一任务与手册摘要；缺接口标 `NEEDS_MANUAL_CONFIGURATION`，由用户在 Grok 原生界面操作后提供读回，不改本地 roster/cache 代替。
3. 对每个在飞旧互审批次核原 actor、真实终态、receipt 和安全交接点，保留其历史；从明确的新批起停止创作者临时互审。无合格 QA 则暂停对应新 review，不虚构 QA 占位身份或把创作者更名当独立会话。
4. 由宿主读回作者/QA当前 native session/run 来源、角色绑定及获准认领入口，用隔离输入核实 QA 的草稿/图像/完整视频能力。成功的 schema 校验或 Bot 自报不替代这些证据。
5. 实际验证一次作者整批直交 QA、QA 自主领取并直交总监；有容量者续领，满额者按 session 停止正式新增。一次回报每岗 responsible scope、共享版本、首个 blocker、下一动作和下次检查，不要求全队复读“收到”。

不能取得的读回一次列齐：总监给原授权与有效任务引用；每作者给当前批/前序 receipt 与真实调用来源；QA 给群成员、独立性、资料/媒体可读性和允许动作；管家给实际 output/execution/publish 根、仓身份及外盘卷绑定；总监给原生检查机制或明确人工唤醒责任。不要发送密钥、完整环境变量或账号隐私。只读缓存的消息与 roster 仅为线索，不证明服务端实时配置、当前活动根或业务完成。

## 完成证据边界

- 配置完成：真实读回按授权槽位的 Bot/群 ID、角色/成员/描述、当前手册摘要、工具/媒体链、native 身份来源与活动根；不是固定成员数断言。
- B 无任务成立：coordination 无 active claim还不够，须连同 execution 与 native 读回证明无在飞/待接管任务；聊天声明不算。
- C 安全切换：逐工作单元旧身份/新规则适用范围、安全交接点、未切换 unknown、唯一 owner、下一动作与下次检查均可回查；不要求全队同步切换，不覆盖历史原件。
- 所有模式：总监当前安排确认与全角色共享事实一致版本均须真实读回；原生检查能力、配置生效、仓库测试、试点产出与正式 M 分别举证。
- READY_READ_ONLY 不等于可生产；claimed、release、账号退出不等于业务完成。缺工具/授权/native事实则报告首个 blocker 和人工下一步，不签发无人值守或重组完成。
