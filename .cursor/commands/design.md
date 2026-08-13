---
name: /design
id: design
category: Specification
description: 记录满足已冻结规格所需的当前有效架构决定，设计期定案对象边界、读写分离与可测试性
---

# /design

目标：记录满足已冻结规格所需的当前有效架构决定。

设计只作用于 AppRoot、L1 和达到门槛的 L2；L3 不创建 `design.md`。L2 只有跨域/服务、外部依赖、状态或所有权变化、迁移、非平凡质量权衡、多方案或特有 rollout/rollback 时创建 design，否则指向父 L1 `DEC-###`。

执行：

1. 读取最小规格父链和 canonical metadata。
2. 写清背景/非目标、所有权、协作与数据流、DEC、失败恢复、特有质量与观测、当前迁移回滚。
3. schema/DTO/path/error 文本不复制，只引用 metadata；类和文件清单回到代码。
4. Story 发现设计缺口时上收到 L2/L1 DEC，并让 Story spec 指向该 DEC。
5. 删除已失效设计，不保留 decision log、revision、兼容方案或历史记录。
6. 运行 `make verify-feature-tree`。

设计期自检（DEC 定稿前逐项确认）：

- **领域模型**：涉及新对象或新成员时，`owned_entity` vs `separate_aggregate` 边界裁决与写 owner 唯一性进入 DEC（裁决问题清单同 `/extend` 对象边界检查）；无界集合禁止内嵌。
- **读写分离**：command/query facet 分流在设计期定案——command 绑定 aggregate owner 与不变量事务，query 绑定业务命名 Reader 与 typed Slice；不留给实现按 URL/DTO/存储类型猜测。
- **可测试性设计**：每个 DEC 声明其行为如何被三层测试观察（导出面、对象级 typed port、provider-state）；只能靠未导出符号或旁路才能验证的决策视为设计缺口，先改设计。
- **运维运营**：失败恢复、SLI/SLO、指标与告警、配置来源、灰度与回滚为必答项；环境证据入口统一 `stackctl`。

设计复述规格、绕过 metadata、缺 owner/一致性/失败恢复、决策不可测试观察或为 L3 建 design 时返回 `GATE_BLOCK`。

自然语言等价触发："设计方案""梳理架构""明确边界/回滚/观测"。
