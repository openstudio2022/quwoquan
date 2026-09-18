# guide · product-ops

按需正文，不进 Reviewer 派发上下文。判据只在 checklist 与命名 evidence，本文件只提供边界解释与违规形态。

owner 规格：[product-ops-growth L1](../../../../../specs/feature-tree/product-ops-growth/spec.md)

## 本领域拥有什么

行为事件、实验定义与分桶事实、运营反馈、策略建议、控制面审计事实、账号治理 case/review/decision 与投递回执，以及面向 App 恢复的各平台当前已发布版本和官方恢复路由事实。对象上下文落在 `quwoquan_service/services/product-ops-service/contracts/product_ops/**`，运营台入口落在 `quwoquan_ops/portal/src/domains/product/**`。

## 三条容易越界的边界

### 跨域写入只走目标领域公开 command

本领域不拥有其他 L1 的事实。需要改动别人的对象时调用对方公开 command，不直写目标存储，也不在本领域复制对方的状态账本——复制出来的那一份在异步窗口里必然与对方产生矛盾事实，恢复时无法判定以谁为准。

账号治理是这条边界最密的地方：本领域只生产经双签的 Suspend/Restore decision 并可靠调用 UserAccount；账号状态、auth epoch、session revoke 与终态事件仍归 user 领域。评审时看的是「decision 产出与投递回执」是否完整，而不是本领域有没有把账号改成想要的状态。

### 指标与建议不替代事实

运营侧产出的是可查询结果，不是业务成功本身。典型违规形态是把指标、实验结论或缓存当成终态来源：

- 业务成功终态由聚合指标反推，而不是来自目标领域公开结果
- App 已发布版本由指标、缓存或本地推断给出，而不是来自 `app_release` 事实
- 实验结论直接改写业务对象，绕过对象自己的写入口

### 热调层只有已声明的那一层

按 [DEC-027](../../../../../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-027) 的四层配置划分，运营可热调的是第三层：限流阈值、feature flag、采样率、文案覆盖与运营开关，判据是「值变化不改变拓扑与依赖身份，且需要分钟级生效与独立回滚」。服务名单、依赖关系与物理地址属于第一、二、四层，改它们是部署事件，必须携带拓扑身份与整体回滚语义，不能做成运营开关。

## 脱敏

事件与审计事实写入前完成脱敏，字段集合以契约声明为准。新增字段既要有声明也要有真实消费方；没有消费方的「先留个字段」不进契约。
