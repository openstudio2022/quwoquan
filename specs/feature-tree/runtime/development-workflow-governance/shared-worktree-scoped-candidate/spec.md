# L3 Story：共享 worktree 范围候选 (`shared-worktree-scoped-candidate`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：本 Story 为横切工程能力，不直接承接用户 Journey。
>
> 设计归属：[L2 DEC-014](../design.md#dec-014)

## 1. 用户价值

作为在lane或integration共享worktree中并行交付的开发者或Agent，我希望先声明不会重叠的整文件修改范围，再用私有Git index构造只包含本范围的exact candidate，从而并行工作不会互相覆盖，也不会把其他writer的dirty bytes带入`dev1.0`。

## 2. 范围与非目标

### In Scope

- path claim的创建、冲突、续租、释放与只读查询。
- 私有index、scope tree closure、candidate commit/request identity与parent漂移。
- lane和integration writer使用同一协议，trusted publisher消费同一请求。

### Out of Scope

- 自动合并冲突、文件内多writer合并、stash/reset/force或清理foreign bytes。
- 环境、设备、package、Git ref与外部系统的并行mutation；这些始终使用独占lease/CAS。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 exact path claim先于写入

- writer必须声明repository-relative、normalized、非空整文件paths及expected parent；路径相等、祖先/后代、rename两端、delete和共享generated output重叠均冲突。
- claim是本地append-only协调事实，绑定owner、worktree、head、scope digest、generation和expiry；过期只允许显式reconcile后释放，不从PID消失自动推导安全。
- query可并行；同一conflict set恰有一个active winner。claim文件只协调本地写入，不冒充Git/Hosted authority。

<a id="req-002"></a>
### REQ-002 私有index与candidate tree闭合

- 每个candidate使用独立`GIT_INDEX_FILE`并从expected parent初始化；只允许stage claimed paths，scope外tree entry必须与parent逐字一致。
- unknown dirty、path escape、symlink目录逃逸、submodule、intent-to-add、越界tree变化、claim/head generation漂移和空scope全部fail closed。
- 成功只写commit object与canonical candidate request，不移动HEAD或ref；request绑定parent、commit/tree、scope、changed-path digest、owner/evidence、ImpactPlan与claim digest。

<a id="req-003"></a>
### REQ-003 publisher CAS与并发恢复

- trusted publisher验证candidate与required source/environment facts后，以expected remote OID执行一次non-force fast-forward CAS并exact readback。
- CAS loser或parent变化必须释放旧claim并从新parent重建candidate及环境事实；unknown outcome先读remote=`before|after|other`，不得盲重试。
- foreign worktree bytes始终留在原处且不进入candidate、不被恢复命令触碰。

## 4. 契约引用

- branch policy：`quwoquan_ops/policies/branch_policy.yaml`
- local readiness：`quwoquan_ops/policies/local_readiness_contract.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多writer只发布本scope

- GIVEN 两个writer在同一worktree基于同一parent申请不重叠或重叠的path scope。
- WHEN 它们创建claim、修改文件并构造candidate。
- THEN 不重叠scope各自产生只含本scope变化且scope外tree等于parent的commit；重叠、越界、未知dirty、claim或parent漂移在写ref前阻断。
- AND publisher竞争只有一个CAS winner，loser从readback得知before/after/other并重建；任一路径都不stash、reset、force或清理foreign bytes。

## 6. 依赖

- 前置要求：[开发流程治理](../spec.md)的owner/evidence与并发边界。
- 下游结果：trusted integration publisher可验证的exact candidate request。
- 父级设计：[L2 DEC-014](../design.md#dec-014)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实多进程与Hosted publisher闭环

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仓内可证明claim/private-index/tree/CAS adapter语义，但真实GitHub App凭据、跨主机claim协调与Hosted ref update/readback仍需外部authority。
- 完成判定：`GWT-001`由真实双writer竞争和Hosted publisher readback直接证明。
- 依赖：受信GitHub App/broker与Hosted ruleset。
