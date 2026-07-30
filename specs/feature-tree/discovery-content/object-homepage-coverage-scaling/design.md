# L2 Design：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“可复用实体主页与多载体内容供给、发布和环境消费闭环”需要 `multi-carrier-release` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：可复用实体主页与多载体内容供给、发布和环境消费闭环。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四载体共享实体目录但保持独立 execution
- 决策：Source Adapter 隔离并校验不可信外部输入；homepage、article、image、video 从同一冻结 canonical entity catalog 独立选目标并并行运行，各自保留 immutable execution。
- 理由：post 只需要稳定 entity identity，不需要等待 entity homepage 生成；独立 execution 才能按载体隔离来源、权利、容量与失败恢复。
- 被否决方案：把四载体塞入同一 execution、让 post 依赖 homepage publish，或由调用方、页面、脚本复制本层状态并绕过公开契约。
- 约束与影响：四载体必须共享 reviewed named main branch、commit、source digest 与 entity catalog digest；detached lane 只继承冻结分支证据而不恢复工作分支，final release 统一验证引用闭包，但单一载体失败不得篡改其他工作包。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
