---
name: /explore
id: explore
category: Workflow
description: 探索模式（定位 L1/L2/L3，冻结风险，不写实现代码）
---

> SDD 主流程：**explore** → prd → design → dev → commit → deploy

探索模式只做思考、分析、澄清和定位，不写实现代码。

## G0 必做项

探索开始前必须自动完成：

1. 查 `specs/feature-tree/tree_index.yaml`，确认需求归属的 `L1_capability`
2. 判断是否需要创建或更新某个 `L2_feature`
3. 判断目标 `L3_story`
4. 查 `contracts/metadata/`，确认涉及哪些业务对象
5. 识别是否涉及扩展场景
6. 识别对标输入、NFR、测试责任、发布风险
7. 识别权限边界、数据生命周期、迁移灰度与回滚风险
8. 若涉及 `path / operation / surface / route / decoder context`，明确 metadata 真相源边界

缺少对标输入、真实网络条件、容量假设、权限边界、生命周期合同或回滚条件时，直接输出 `GATE_BLOCK`。

## 三层定位原则

- `L1_capability`：能力边界
- `L2_feature`：稳定业务特性容器
- `L3_story`：最小独立交付单元
- `Task`：执行方向，只做初步拆解，不建目录

禁止：

- 在 explore 阶段讨论 `L4/L5`
- 把任务项当成树节点

## 探索重点

- 目标用户是谁
- 核心问题是什么
- 成功标准是什么
- 不做什么
- 是否有对标产品、原型、截图、视频、公开代码或公开文档
- 该需求应挂到哪个 `L1_capability`
- 应形成哪个 `L2_feature`
- 目标 `L3_story` 是什么
- 是否涉及权限、分享、小趣消费、删除撤销、升级迁移
- 初步 Task 方向是否满足 `metadata -> codegen -> 业务逻辑 -> 测试`

## 输出建议

```text
已澄清：
- ...

仍待澄清：
- ...

建议归属：
- L1: ...
- L2: ...
- L3: ...

初步任务方向：
- Task: ...

商用风险：
- Benchmark:
- SLO/KPI:
- 权限/生命周期:
- 灰度/回滚:

测试责任：
- T1: ...
- T2: ...
- T3: ...
- T4: ...

结论：
- EXPLORE_READY
# 或
- GATE_BLOCK
```

## Guardrails

- 不实现代码
- 不创建第四层或第五层树节点
- 不把测试层写成 `L3/L4`
