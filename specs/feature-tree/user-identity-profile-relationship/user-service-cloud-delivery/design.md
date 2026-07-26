# L2 Design：用户服务云端交付 (`user-service-cloud-delivery`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新”需要 `remote-profile-delivery` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`remote-profile-delivery`](./remote-profile-delivery/spec.md)：App 必须经 generated operation/Facet 读写资料；请求失败不得返回 Mock 或本地合成成功，切换主体后必须清除旧主体投影。

## 3. 端云与数据流

- 上游能力：身份进入和授权上下文。
- 下游能力：个人主页、关系列表、设置及使用用户资料的其他领域。
- 读取事实：用户、关系和设置 owner projection。
- 写入事实：仅通过 user-service 公开 command。
- operation/event/object/error：引用 `quwoquan_service/services/user-service/contracts/`。
- 一致性要求：资料更新、缓存失效和 projection 版本必须可观测；不得双写 Mock 状态。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 对象专属 command/store 与 named reader
- 决策：对象专属 command/store 与 named reader。
- 理由：让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`remote-profile-delivery`](./remote-profile-delivery/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 记录 operation、对象 ID、版本、缓存命中、存储延迟和 canonical error；不记录敏感资料值。
- user-service 在必需依赖缺失时 fail-fast，四环境配置与部署入口保持一一对应。
- 灰度以 service deployment 为原子边界；回滚不得恢复旧 wire 或双写路径。
