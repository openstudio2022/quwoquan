# Design: Cloud-Network Error Display Contract

## 设计动因

规范 `specs/ux/error-and-permission-semantics.md` §1 的落地实现。

## 关键决策

阻塞性用内联、次要用 SnackBar，与 Material Design Errors 模式一致。

## 适用场景与约束

适用：所有涉及云端请求的页面。不适用：纯本地逻辑。

## 测试策略（交互异常覆盖）

**动因**：仅断言 l10n key 存在的测试价值低。核心需在**交互过程**中测试异常态（权限拒绝、云端超时、加载失败）。

**目录约定**（按领域服务划分）：
- 无 `test/cloud/integration/` 顶层；content 领域使用 location → `test/cloud/content/location/`
- 位置选择页属于创作入口 → `test/ui/content/entry/widgets/`

**L1b 策略**：先 CloudException 路径（FakeChecker 返回 granted + FakeLocationService 抛异常），再权限拒绝路径（依赖 permission-card 的 LocationPermissionChecker）。

**适用场景与约束**：L1b 依赖 permission-card 的 LocationPermissionChecker 抽取完成。

## 未来演进

抽取 CloudErrorInlinePlaceholder 共享组件。
