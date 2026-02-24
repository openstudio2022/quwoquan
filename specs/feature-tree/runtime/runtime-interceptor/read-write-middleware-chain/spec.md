# L3 子特性：read-write-middleware-chain

## 功能说明
- **读链（Read Chain）**：在 Repository 返回数据前执行，按顺序：api_exposure 过滤 → classification 脱敏 → log_policy 日志。
- **写链（Write Chain）**：在 Repository 写入数据前/后执行，按顺序：NOT_NULL 校验 → 类型校验 → 写入 → 事件 hook → 指标。
- **Interceptor 模式**：定义 ReadInterceptor、WriteInterceptor 接口，支持链式组合，注入 Repository 层。

## 实现要点
- **接口定义**：ReadInterceptor(ctx, entity) → entity；WriteInterceptor(ctx, entity, op) → error。
- **链执行**：按注册顺序依次执行，任一失败则中断。
- **Repository 集成**：Repository 实现层在 FindByID/Save 中调用链，对调用方透明。

## 约束
- 链规则 100% 由 fields.yaml 驱动。
- 链执行失败必须返回明确错误。

## 验收标准
- A1：读链/写链按顺序正确执行。
- A6：SECRET 在读链中 drop。
- A7：规则与 fields.yaml 一致。
