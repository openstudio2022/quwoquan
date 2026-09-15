# L3 Story：canonical 内容身份的显式治理修复 (`canonical-content-identity-recovery`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-023](../design.md#dec-023)

## 1. 用户价值

作为内容运营者，我希望当前池每个对象有明确的有效性与依赖证据，能按精确清单迁移到唯一新契约或经授权退役删除；历史审计保持原字节，活跃池不留下旧架构或无限期 excluded，治理不成为 producer 的自动 recovery 或 scheduler。

## 2. 范围与非目标

### In Scope

- 全部当前池对象的互斥有效性、身份占用、最深层错误与依赖闭包。
- 精确迁移或删除清单、证据裁决、独立内容仓 staging、完整新池校验与授权切换；实现许可不代替实际搬迁、仓初始化、提交或删除授权。
- 地域、名称、分类与分区整理时逻辑身份守恒，目录条目号与内容版本分离。
- 历史审计及被引用媒体的字节保护；普通运行路径零旧契约兼容。

### Out of Scope

- 正常合格对象的入池路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- 自动 repair process manager、调度解饥饿、nextAction/reentry 状态机。
- immutable release producer handoff（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）与下游环境消费（由环境 owner 独立拥有）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 当前对象以充分证据迁移或精确退役，旧运行契约不得遗留

- 统一池 reader 只接受显式新契约 record 与完整 admission、稳定身份、来源及权利事实，不从 review、目录名或当前配置补造。查询分开身份不存在、当前有效与存在但无效；最深层 typed error 和依赖必须保留，invalid 不当作 absent 或已完成。
- 切换输入覆盖全部活跃对象与依赖，每个对象只能选择有证据迁移或按授权退役删除；清单绑定 before identity/digest 与 after 预期。未裁决、遗漏或证据冲突保持阻断，不允许永久 excluded 或旁路旧池。
- 迁移保留逻辑身份、资产顺序和真实来源，以受测转换生成新版本、record 与摘要。纯格式转换必须验证原始证据；payload drift 或权利无效需补足实际事实和独立 review，不得靠刷新摘要或补 passed 伪造资格。
- 不能迁移的对象连同无法修复的依赖精确退出活跃树，保留终态裁决与历史证据。删除前校验当前池、历史 release、rollback、环境绑定及媒体引用保护闭包，不误删仍被引用的 exact bytes。
- 对仍在运行的旧根替换，完整新池在隔离 staging 校验后 CAS 切换，失败保持原状态。旧根已退出运行输入、正式独立仓已存在时，只按精确清单逐对象迁入完整新包；复用现有单对象 audit/CAS 与先依赖后引用顺序，不交换仓根、不增加对象激活。单事务失败不留下半包，不撤销其他成功对象；按实际回执从首个未闭合对象续跑，不承诺整批原子性。旧树清理另守保护与授权，不整池 reset。
- 历史 Git、receipt/release 审计保持原字节，仅可按原提交/制品离线复核；普通 publisher、reader 与消费者拒绝旧输入，不保留双读双写或自动 repair manager。迁移专用旧解析能力完成后撤下。

<a id="req-002"></a>
### REQ-002 存储整理保留业务身份与已审核字节

- 实体 ref、实体 ID、作品 ID 与消费者主页 ID 均不随目录移动、名称/分类/地域整理或分区变化而重算；既有 ref 即使外形像旧路径也作为 opaque 逻辑身份。consumer 从 manifest 读身份，不从目录段数或名称推导。
- 同名不同实体显式使用不同稳定身份，两个区县同名对象可独立 init；同物新版本沿用业务身份并递增内容版本，另分配组内新条目，不由末级数字推断版本。唯一对象里程碑不重复累计版本。相同规范名称、类型、主行政归属及可证同一主来源实体却占用不同 `entityId/entityRef` 时视为跨 ref 身份冲突，不得再调用普通 publish 或 `revise-homepage` 追加所谓新版本；身份 owner 必须以 expected-before 摘要裁定唯一保留身份、全部当前依赖迁移与另一身份退役，完成前两个身份均不得被 Bot 当作版本候选。
- 已发布 homepage 的事实更正只经显式单对象治理入口：宿主确认目标与理由，输入新 execution、原 ref、expected current version 与 payload digest；新 execution 不以 passed 前序作 retryOf，须完成自己的真实来源、创作与不同 session/runId 的独立 review。新包保留 ID/ref，版本只取 expected + 1，另分配 locator；普通 publish 不开放覆盖参数。
- 共享内容仓锁内核对 before 版本及实际 payload 摘要，再复用对象 package/audit/apply；新包、record 与新 review 绑定一致才写入。任一漂移、无新独立审核或身份变化零 pool 写；同一输入 exact replay 不追加版本或 record，变化输入不得借旧包重放。查询按同身份最高版本选择，旧包、review、receipt 与 release 原字节不动，不建修复 runner 或第二台账。
- 纯 locator 变化不改变包内摘要、媒体摘要或 review 原件；契约转换、合并 manifest 或任何包字节变化必须生成新版本/摘要并保留原审核 binding，不能刷新旧 receipt 冒充重新审核。
- 迁移清单区分元数据、完整包与交付 bundle，在共享写锁下冻结全部未提交/未跟踪对象、采用来源、媒体、旧 release/receipt 与保护集；验证独立备份后才允许授权切换。新根枚举只遍历对象根，仓元数据、Git 与 releases 不算对象。
- 独立仓切换不交换包含 Git 管理目录的仓根；staging、expected-before 与失败恢复复用既有事务边界。实际搬迁、旧树删除、仓 init/clone、commit/push、远端备份及环境激活各守授权，不用某一工作树配置声称所有 lane 已切换。

## 4. 契约引用

- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- canonical object transaction：对象级 package/apply schema

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 全对象硬切保持身份、依赖、媒体与审计闭包

- GIVEN 通过真实对象事务创建的当前池包含有效对象、存储边界注入的 payload drift、权利证据无效对象及依赖帖子，且有绑定 before 摘要的精确迁移或删除清单与保护集。
- WHEN 运营者先只读查询，再在取得相应授权后执行受治理 cutover。
- THEN 查询保留最深层 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 或权利错误与 exact objectRef，不把 invalid 判作 absent 或已完成；清单缺项、证据不足、动作歧义与依赖悬空均拒绝。
- THEN 充分证据对象保留逻辑身份、来源与资产顺序，以新版本和摘要满足唯一新 schema；不能迁移的对象及无法修复的依赖逐项退役删除，全部原对象有终态，活跃树无旧记录与兼容读取。
- THEN 在 staging、校验、CAS 切换处注入失败或并发变更时原状态不变，成功时只有一个完整活跃池；普通 publish 不接受旧 schema 或特殊覆盖，旧 release 不能经新 reader 激活。
- THEN 历史 receipt/release 与保护媒体的 exact bytes 不变，删除只命中清单授权对象；输出 before/after 与逐对象结果，撤下迁移旧解析能力，不创建自动重试、repair manager 或长期 legacy 队列。

<a id="gwt-002"></a>
### GWT-002 地域与同名整理不改变稳定身份

- GIVEN 两个不同区县的同名地点、同区县同名不同对象及一个已有新版本的对象都具有显式稳定身份。
- WHEN 分别独立 init、发布新条目，并执行已授权的名称/分类/地域/分区整理。
- THEN 各对象的实体 ref、实体 ID、作品 ID 与原主页 ID 均保持对应关系而不串跳，目录末级序号不作为版本，重复版本不增加唯一对象计数。
- THEN 同一真实实体跨 ref 重复占用不得通过所谓 v2/v3 或 `revise-homepage` 扩散；缺身份 owner 的 expected-before、依赖闭包与退役裁定时保持阻断。完成治理后当前 reader/consumer 只返回唯一生效身份及其最高内容版本，旧身份/旧版本仅离线审计，不建立别名双读、版本选择或兼容分支，归并引起的计数下降不算负产量。
- THEN 纯移动的包/review/媒体摘要不变，包字节转换只产生新版本及新摘要并保留原 review binding，旧审核与 release 不重写。

<a id="gwt-003"></a>
### GWT-003 独立仓切换受完整快照、保护集与精确授权约束

- GIVEN 当前池含未提交/未跟踪内容、来源证据、媒体及历史 release，独立内容仓身份已声明但尚未获实际搬迁/删除授权。
- WHEN 生成全量 before 与隔离 staging，验证独立备份、对象闭包与 old/new 定位清单，再分别注入并发漂移和切换阶段故障。
- THEN 无授权只产生准备证据而不移动或删除当前数据，缺项、备份不符或 before 漂移均阻断，旧池与历史原件保持原字节。
- THEN 授权切换只使完整已验证对象集单轨可见而不交换 Git 仓根，Git/仓 metadata/releases 不进入对象枚举，输出 exact old/new identity、版本、包/来源/媒体守恒结果，不据本 lane 配置声称全局切换。
- THEN 旧根已退出运行时，逐对象迁入按实际 objectPath 保存完整包，业务 ref 不变；合法无图对象可迁入，包缺项/摘要漂移仍拒绝。重复调用同包不增加对象或记录；中途单笔失败保留其他成功成品，恢复按原回执继续，不再执行全批激活。

<a id="gwt-004"></a>
### GWT-004 新审核驱动同身份事实修正且旧版本不可变

- GIVEN 真实对象事务生成的 v1 homepage 与独立的新 correction execution，宿主已确认 exact 目标、before 版本/摘要和修正理由。
- WHEN 经治理入口提交正文与主行政归属的更正，新 execution 持有自己的来源、author 与独立 reviewer 的完整通过证据。
- THEN 新 locator 上 v2 的 ID/ref 与 v1 相同，新 record 的内容版本/包/审核摘要一致，正文与主行政归属来自新审核成品。
- THEN 查询选择 v2，旧对象树及 review/receipt 原字节不变，唯一对象计数不增。
- THEN stale 版本或摘要、审核缺失/不独立/错绑、不同 ID/ref 均在 pool 写入前拒绝。
- THEN 同输入 exact replay 无新增，输入或已写新包漂移拒绝，不把旧 v1 改摘要当作新版本。

<a id="gwt-005"></a>
### GWT-005 已发布文章图片视频同身份修订不换标题绕重

- GIVEN 已发布 article、image 或 video 对象存在事实或媒体错误，且当前身份占用有效。
- WHEN 运营者请求同身份修正。
- THEN 不得以新标题或新 ID 绕过占用身份重新创建。
- THEN 在通用修订入口未证明前，该纠正保持阻断并交治理 owner。

## 6. 依赖

- 前置要求：canonical pool 的 create-once record 与对象事务单写者语义。
- 上游事实：payload/record digest 事实与治理侧 fresh evidence。
- 下游结果：可裁决的 invalid 状态与恢复动作，供 publish AI 与 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的显式 release cohort 选择消费。
- 父级设计：`DEC-023`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 当前池显式迁移或删除与原子切换尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：现有工作树已实现显式 `pool-cutover snapshot/dry-run/activate/inspect/cleanup` 与只读原 authority 盘点，但尚缺真实全池迁移验收证据，命令存在及临时 fixture 的局部通过不代表完成；既有 sequence 前进仍不证明当前 payload/rights 有效。
- 尚缺实现与证据：覆盖当前全部对象的受测新包转换、逐项裁决与依赖闭包，以及经精确授权的真实 CAS/退役/旧树清理结果。manifest 单源的 JSON 投影复验已与 publisher 共用资产/取得/派生绑定，并覆盖说明、摘要、字节及引用篡改拒绝；离线来源摘要只归一 singular/plural 引用与空旧字段，真实来源、资产身份和顺序仍不可漂移。独立 spawn 已验证提交点前后进程故障与并发唯一胜者，临时 fixture 不能代替真实全池验收。普通读写零旧契约兼容，原始 review/receipt、媒体与历史 release 不改写。
- 新布局接续缺口：现有 cutover 的 snapshot、原链/package 复验与 activation 仍含旧 `_pool/versions`、`_entity.json`、逻辑 ref 等同物理路径及整根 exchange 假设，不能用于带 `.git` 的独立内容仓。需先按现役事务边界核对 staging 与当前活跃快照的合并及提交方式；旧池已离开现役输入时，不得以旧根替换方案丢弃当前仓新增对象。转换包的 schema/record/source 或 pool-query 通过，也不代替 candidate 图片冲突、同实体别名与原权利投影差异的逐项裁定。当前命名运行证据见 `.qwq_output/data/local/workspace/content-production/m1000-recovery/rounds/r00/report.md`；未取得完整准出及实际授权结果前保持本 OPEN。
- 完成判定：[`GWT-001`](#gwt-001) 与 [`GWT-003`](#gwt-003) 由真实对象事务及存储边界 fault injection 验证；全量当前对象在独立仓 staging 有明确映射/终态，实际迁移或退役只在逐项授权后完成。原错误不被摘要刷新掩盖，当前池无旧结构、悬空依赖或遗漏对象，历史审计原字节不变。
- 最小测试入口：复用 `quwoquan_data/tests/local_contract/release/` 现有 pool-cutover snapshot/dry-run/activate/cleanup 测试，对新增 `GWT-003.t1`、`GWT-003.t2` 作子句级绑定；fixture 只证明机制，真实全量快照/备份/授权切换另取证，不以测试临时仓冒充真实切换。
- 依赖：单轨 schema 与消费者先行；精确删除授权、真实来源/独立 review、媒体保护和事务边界遵守 [L2 DEC-023](../design.md#dec-023)。

<a id="open-002"></a>
### OPEN-002 目录定位与稳定身份解耦尚缺端到端证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 locator 与业务身份解耦的端到端证据。现有身份/转换成果保留；新地域与同名布局必须证明不同区县同名实体独立 init、不串跳，同物新版本不重复计数，不能仅凭目录测试声明身份守恒。
- 尚缺实现：显式身份读取、locator 分配、真实 Entity importer 与 Content mention 映射的同快照回归；纯移动与包字节转换必须分别验证原 review binding。
- 同身份事实修正增量：[`GWT-004`](#gwt-004) 的本地机制证据与真实运营证据分层验收，实际对象的新独立审核、授权发布与下游身份读回仍由宿主点名执行，临时 fixture 不代表端到端闭合。
- 完成判定：[`GWT-002`](#gwt-002) 全部子句在最小 Data identity/object-transaction local_contract 和真实 Entity importer 映射 api_integration 直接绑定；实际存量迁移仍由 `OPEN-001` 验收。
- 依赖：`quwoquan_data/tests/local_contract/release/` 的 identity/pool-cutover 测试、entity-service homepage importer 与 content-service release importer 现有测试；新代码 owner 按实际 path PRE 认领，不用本 Story PRE 冒充源码归属。

<a id="open-003"></a>
### OPEN-003 已发布文章图片视频同身份修订尚未证明

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：homepage 已有 `revise-homepage`。已发布文章、图片、视频的同身份新版入口未证明。不能换标题绕重，也不能只靠新 Bot 提示词宣称存量错误已纠正。
- 尚缺实现与证据：article/image/video 的显式修订 command、新独立 review 与旧包不可变读回。
- 完成判定：[`GWT-005`](#gwt-005) 由真实对象事务证明同身份新版本、旧字节不变且不得绕重创建。homepage 路径继续由 [`GWT-004`](#gwt-004) 拥有。
- 依赖：对象事务 owner 与明确修订授权。内容团队不自行发明第二身份。
