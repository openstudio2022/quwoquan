# L2 Business Capability：<中文名称> (`<l2-id>`)

> 所属领域：[<L1 名称>](../spec.md)
>
> 设计归属：`本层 design.md` 或 `[L1 DEC-001](../design.md#dec-001)`

## 1. 能力目标

说明这组 Story 为用户、运营方或平台调用方组合出什么独立业务结果。

## 2. 范围与非目标

### In Scope

- ……

### Out of Scope

- ……
- 由 [`<other-l2-id>`](../<other-l2-id>/spec.md) 负责：……

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-001`](../../spec.md#scn-001)
  - 本能力接收：……
  - 本能力处理：……
  - 本能力输出：……
  - 失败时终态：……

## 4. Story

- [`<l3-id>`](./<l3-id>/spec.md)：<最小独立价值>

列表必须与直接 L3 子目录一致。

## 5. 能力要求

### REQ-001 <要求标题>

- 必须……
- 不得……
- 契约引用：<canonical contract ID；不适用则删除>

## 6. 契约与依赖

- 上游能力：……
- 下游能力：……
- 读取事实：……
- 写入事实：……
- operation / event / surface：<仅引用 canonical ID>
- 一致性要求：……

## 7. 集成验收

### SIT-001 <跨 Story 或端云组合行为>

- GIVEN ……
- WHEN ……
- THEN ……
- AND ……

只保留影响业务契约的代表场景，详尽边界进入测试。

## 8. 开放事项

仅记录本能力跨 Story 的未完成事项；字段格式与 L1 相同。
