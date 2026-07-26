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

设计复述规格、绕过 metadata、缺 owner/一致性/失败恢复或为 L3 建 design 时返回 `GATE_BLOCK`。

自然语言等价触发：“设计方案”“梳理架构”“明确边界/回滚/观测”。
