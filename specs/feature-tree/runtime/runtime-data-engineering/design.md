# L2 Design：运行时数据工程 (`runtime-data-engineering`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入”需要 `article-commercial-scale-closure`、`geo-content-trinity`、`image-commercial-scale-closure`、`video-commercial-scale-closure` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：图片来源、下载字节、授权与发布引用均可回放。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：缺任一 required rights 字段的资产不能进入 release。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：不满足 admission 的候选以 typed issue 阻断。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 数据任务先冻结来源事实并经 immutable release 激活
- 决策：数据任务先冻结 reviewed commit、source digest、canonical entity catalog、来源、权利与目标事实，并让各 carrier 以独立 execution 并行运行后再经 canonical publish、immutable release 和环境 importer 激活。
- 理由：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 被否决方案：环境 seed manifest、T3/UAT 自建业务对象、post 依赖 homepage execution、把四载体塞入单一 execution，或调用方/页面复制本层状态并绕过 release/importer。
- 约束与影响：release 聚合以冻结的 source/entity facts 和独立 carrier execution 为输入，用 attestation `payloadSha256` 串联四环境 import/readiness，并在 cleanup 时以进程锁及 acceptance evidence 保留长期验收引用。
- 关联要求：`REQ-001`
- 影响 Story：[`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)、[`geo-content-trinity`](./geo-content-trinity/spec.md)、[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)、[`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
