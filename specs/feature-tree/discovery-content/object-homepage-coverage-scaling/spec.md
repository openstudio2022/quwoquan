# L2 Business Capability：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

可复用实体主页与多载体内容供给、发布和环境消费闭环。

## 2. 范围与非目标

### In Scope

- family、provider policy、reference 与 execution request 的职责隔离。
- entity homepage、article、image、video 的六步生产、review、canonical publish 与 release。
- 与源码工作树平级的独立内容仓、地域优先的对象定位、稳定身份与可独立复制的最终对象包。
- immutable release handoff；以及由下游环境 owner 独立拥有的导入、API 验证、App 消费、rollback 与 replay 证据。

### Out of Scope

- 任何特定区域、实体、目标数量或活动阶段的运行计划。
- 非地点 producer、自动重分区、引用健康服务、后台逐图探活或自动修复。
- 新增跨服务强一致、普通实体下线的级联删除、跨端缓存失效广播；既有发布激活 fence 保持原 owner。
- 异卷或远端备份的部署、恢复目标与运维周期的具体取值；未验证的耐久性由 `OPEN-002` 如实保持未建立。

## 3. Journey / Scenario 贡献

- [`JNY-014 / SCN-035`](../../spec.md#scn-035)
  - 本能力接收：内容运营者 confirmed 按需请求（范围、载体组合、逐载体数量、来源策略）与 canonical 输入。
  - 本能力处理：可复用实体主页与多载体内容供给、发布和环境消费闭环。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story

- [`work-request-compilation`](./work-request-compilation/spec.md)：confirmed 按需意图收敛为现役逐载体 demand 与 immutable candidate bindings；旧 handoff/WorkRequest/request-envelope schema 已删除。
- [`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md)：所选载体生产、来源/媒体准入、article 来源预筛与唯一 reviewed delivery 入池路径，终点为 canonical pool record 与可恢复 typed 终态。
- [`source-discovery-scale-reliability`](./source-discovery-scale-reliability/spec.md)：来源发现由宿主 AI 原生串并行，仓内 worker/slot/heartbeat 控制面退役。
- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用，运行 receipt 只能写入输出目录、不得回写静态真相源；immutable release handoff 是 producer 终点；环境导入与 App 消费由下游环境 owner 只读 handoff 后独立闭合。
- [`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md)：invalid canonical identity 只通过显式对象治理 query/command 收敛，不成为内容生产自动恢复。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 可复用内容 execution 与发布 SIT

- 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- 每次 release 只消费调用方显式给出的 exact cohort；日常 publish 允许 partial 并保留全部合格对象。
- 文章配图率、素材来源分布、视频热度与宿主实际并发仅作外部诊断，不进入 Data 业务 authority。
- homepage/article/image/video execution 可由宿主原生串行或重叠运行，不要求固定并发。每个 stage 的 verdict/typed issues 由宿主 AI 显式提交；共享 canonical 只经单对象事务，release 只消费显式 cohort。
- 宿主并发、截止、模型与会话重启不进入 execution 或仓库配置。对象下限与工作单元数相互独立；宿主运行能力不得成为第三个业务 authority。
- release handoff 只绑定 immutable producer facts；环境 receipt、rollback/replay 由下游 owner 通过既有 ship/Ops 能力写入自身输出，不进入 producer stage chain。

<a id="req-002"></a>
### REQ-002 `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属

- `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属；不得写来源 URL 或运行结论。
- 静态资产不得包含区域、实体、日期、数量、运行路径或活动阶段；这些值只在 `0.plan` 冻结。
- 每个发布对象必须有 source、媒体处置、creator/tag 引用、review 与 execution source digest。
- 运行 profile、schema、provider policy 或 target set 改变时，必须创建新 execution，并以 `retryOf` 关联重试。
- 环境导入、API 与 App 消费未完成时保留对应 `GATE_BLOCK`；静态目录与本地 gate 不得冒充环境交付。

<a id="req-003"></a>
### REQ-003 随体媒体可兑现与独立备份的耐久性诚实呈现

- 四载体最终对象包必须携带实际交付媒体及采用来源的必要证据，普通完整复制后不依赖原 execution、content library 或来源网站；元数据 Git 检出不是完整媒体副本。静态输入可重建的承诺不覆盖外部网页、AI 判断或已派生媒体字节。
- content library 继续用于采集复用，独立 golden media 备份与对象随体媒体按摘要互相校验。硬链接不是独立备份，`.gitignore` 不是保护；同卷两份完整拷贝只证明两份副本，不证明抗卷损坏。没有经验证的异卷或远端恢复证据时，该层耐久性必须显示未建立。
- 生产发布、闭包验证与部署消费必须对缺失或摘要/大小不一致的具体引用 fail closed；完整媒体根不可达、单文件缺失、字节损坏和来源证据缺失可区分，不能以空路径、零大小或隐式跳过冒充完成。浏览时的单媒体失败仅影响局部展示，不把发布闸口误用为整页运行失败。
- verify 与普通消费只读，不下载、不回填库、不修复包；恢复由显式操作在隔离目标逐摘要验证，不能承诺来源 URL 能重新生成同一转码字节。任何保留作品、release 或审计仍引用的媒体均在保护集内。
- 耐久性与真实恢复由本层 `SIT-002` 验收；具体备份部署及恢复目标由 Data/Ops 授权裁决，不新增周期健康框架，也不复制生产数据库的 RPO/RTO。

<a id="req-004"></a>
### REQ-004 独立内容仓与稳定业务引用互不代偿

- canonical 内容由与源码工作树平级的独立 Git 仓拥有，不是源码 worktree、submodule 或 symlink；源码只拥有规则、schema、CLI 与测试。仓身份缺失或不符必须阻断，不能回退旧仓内目录。
- 有地理归属的实体按真实主行政链管理，主类型沿用已有 taxonomy；posts 按载体与主分类管理，不因引用多个地区复制作品。名称、分类、地域与分区只决定物理定位，实体和作品的稳定 ID/ref 不由目录重新推导。
- 实体、标签与平台创作者保持共享业务身份；作品内聚采用来源及媒体，不复制主体身份或建立全球来源解析服务。
- 发布构建校验所选对象的显式内部引用闭包；运行正文使用名称快照，点击才由目标 owner 校验可见性。普通实体下线不下线引用作品、不改原文、媒体或历史 release；权限检查不被弱一致豁免。
- 目录与引用的可独立验收行为归直属 Story；单对象原子 publish、仓级共享写锁与既有 release/fence 的边界由本层 design 冻结。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 可复用内容 execution 与发布 SIT

- GIVEN 执行“可复用内容 execution 与发布”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“可复用内容 execution 与发布”对应动作。
- THEN 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- THEN execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- THEN 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- THEN release 只消费显式 exact cohort；未合格对象不进入 cohort，已合格对象可形成 partial production release。
- THEN 文章配图、来源分布、视频热度与宿主实际重叠只作诊断，不形成业务 authority。
- THEN 每个实际启动的 task 分别形成 typed 终态；排队、未启动或诊断 sample 不算 task 结果。canonical publish 以单写对象事务接收已合格对象，最终 Manifest/release 对被选对象及引用做 exact closure。
- THEN 对象下限与工作单元数独立冻结；宿主并发/截止不写入 execution，receipt 不记录宿主调度 authority。
- THEN release handoff 只绑定 immutable producer facts；环境 receipt、rollback/replay 由下游 owner 通过既有 ship/Ops 能力写入自身输出，不进入 producer stage chain。

<a id="sit-002"></a>
### SIT-002 随体媒体可独立消费且真实恢复与局部故障分层验收

- GIVEN 四载体最终包及所选 release 均声明 exact 媒体，另有独立备份；原 execution/library 与来源站点均不可用。
- WHEN 将完整作品复制到隔离目标只读校验，并分别构造媒体根不可达、单文件缺失、摘要漂移与显式恢复情形。
- THEN 完整包及由其物化的 release 仍可按摘要校验并消费，不需要原 execution/library，不隐式下载或修复。
- THEN 发布/部署校验对单文件缺失或摘要/大小不符返回定位到该引用的 typed 失败，不以空字节、跳过或旧成功证据代偿。
- THEN 媒体根整体不可达与单文件失效可区分，来源证据缺失也不被报告为媒体缺失；运行局部失败不清空其它已可读内容。
- THEN 独立备份经显式操作在隔离目标证明 exact-byte 恢复后才承认该层恢复能力；同卷副本或硬链接不能声明抗卷损坏，未验证异卷/远端备份时其耐久性仍未建立。
- THEN 源站不可达不影响随体成品；校验不执行恢复，来源 URL 或重新派生不被当作 exact-byte 恢复保证。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 可复用内容 execution 与发布 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 `SIT-001` 的子句级 `spec_ref` 绑定。可复用内容 execution 与发布链存在历史走通实例，但 producer 六步 `release -> END` 与完整 immutable handoff 仍缺 current 同 revision 复合证据，静态 family、provider、schema、prompt/template 与 reference 不含运行实例值的目标保持有效，但组合行为尚无直接测试证据锚定。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 随体媒体独立恢复与异卷耐久性尚未验证

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：已有 content library 与 golden media 保护/恢复成果必须保留；本次不再把 library 当作唯一 holder。仍缺完整作品脱离原库、显式恢复与真实独立备份的同快照证据，不能从两个配置路径、硬链接或同卷副本推出抗卷损坏能力。
- 尚缺实现与证据：按新随体对象包完成只读校验与显式恢复边界，分别验证根不可达、文件缺失、摘要漂移及来源证据缺失；在获授权隔离目标上核验真实备份恢复。异卷/远端未建立时持续明示该层未建立，不增加周期健康服务或自动修复。
- 完成判定：`SIT-002` 全部结果子句按当前对象包契约成立，且 `SIT-002.t4` 有真实独立备份与隔离恢复证据，原媒体及审计字节不变。
- 依赖：Data/Ops 的显式备份与恢复授权；既有 `quwoquan_data/tests/local_contract/release/test_media_holding_closure__library_sole_holder__reliability__local_contract_test.py` 需改验新随体语义，旧 sole-holder 测试即使通过也不关闭本 OPEN。包级缺口由 `multi-carrier-release` 的 `OPEN-025` 承接，环境消费由其 `OPEN-015` 承接。
