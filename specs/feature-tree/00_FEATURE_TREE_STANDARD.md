# 特性树文档标准（三层目录版）

> **权威**：特性树节点的治理信息只通过以下四类文档表达：
>
> - `spec.md`
> - `design.md`
> - `tasks.md`
> - `acceptance.yaml`
>
> 本标准与三层层级定义绑定，只适用于：
>
> - `L1_capability`
> - `L2_feature`
> - `L3_story`
>
> `Task` 只存在于任务文档中，不占目录层。

---

## 一、适用范围

本标准适用于全仓端云一体化开发，包括：

- `quwoquan_app`
- `quwoquan_service`
- `contracts/metadata`
- `specs/feature-tree`

任何子域规范只能补充细节，不能替代本标准。

---

## 二、四类文档

### 2.1 `L1_capability`

每个 `L1_capability` 目录必须具备以下四类文档：

- `spec.md`
- `design.md`
- `tasks.md`
- `acceptance.yaml`

职责：

- 说明能力边界
- 说明关键旅程、NFR、发布治理
- 组织其下的 `L2_feature`

### 2.2 `L2_feature`

每个 `L2_feature` 目录必须具备以下四类文档：

- `spec.md`
- `design.md`
- `tasks.md`
- `acceptance.yaml`

职责：

- 作为稳定业务特性容器
- 承载 Feature 范围、边界、聚合规则与 Feature 级验收

### 2.3 `L3_story`

每个 `L3_story` 目录必须具备以下四类文档：

- `spec.md`
- `design.md`
- `tasks.md`
- `acceptance.yaml`

职责：

- 作为最小独立交付单元
- 承载规格、设计、任务、验收和测试证据

### 2.4 `Task`

`Task` 不拥有独立目录，也不拥有独立四件套。  
它只存在于 `tasks.md` 或后续 `tasks.yaml` 中。

禁止行为：

- 为 `Task` 建目录
- 为 `Task` 建独立 `spec.md`
- 为 `Task` 建独立 `design.md`
- 为 `Task` 建独立 `acceptance.yaml`

---

## 三、四类文档职责

| 文档 | 作用 |
|------|------|
| `spec.md` | 说明做什么、不做什么、为什么做、适用边界 |
| `design.md` | 说明怎么做、为什么这样做、方案对比、关键决策 |
| `tasks.md` | 说明 `Task` 执行清单、搁置项、未来演进项 |
| `acceptance.yaml` | 说明验收标准、测试层映射、证据、执行门禁 |

### 3.1 禁止第五类治理文档

禁止在特性树节点下新增以下独立治理文档：

- `analysis-*.md`
- `README.md`
- `architecture.md`
- `diagram.md`
- `*-规划.md`
- `*-设计说明.md`

分析、规划、架构说明、图示说明都必须汇入四件套内部。

---

## 四、文档内容要求

### 4.1 `spec.md`

必须包含：

- 节点层级与定位
- 背景与动机
- 目标用户或平台价值
- 功能范围
- Out of Scope
- 约束与适用边界
- 对标输入与吸收结论
- 验收重点

### 4.2 `design.md`

必须包含：

- 设计动因
- 上游输入评审
- 对标输入分析
- 至少两套方案对比
- 选型决策
- 关键设计决策
- TDD / ATDD 策略
- 未来演进

若是 `L1_capability`，还必须在 `design.md` 内包含架构图示或等价文本说明，不得外置第五类文档。

### 4.3 `tasks.md`

必须包含三个标准区块：

- 当前交付任务
- 搁置任务（带规划）
- 未来演进任务

约束：

- `tasks.md` 是 `Task` 的唯一正式承载位置
- `tasks.md` 不是树层级
- 任务应回链到 `acceptance.yaml` 的验收项

### 4.4 `acceptance.yaml`

必须包含：

- `feature`
- `level`
- `execution`
- `level_acceptance`

每个核心验收项至少包含：

- `criteria`
- `status`
- `linked_tasks`
- `test_layers`
- `tests`

测试层只允许使用：

- `T1`
- `T2`
- `T3`
- `T4`

---

## 五、目录与索引规则

- 特性树目录只允许三层目录深度：`L1_capability / L2_feature / L3_story`
- `tree_index.yaml` 是索引唯一真相源
- 不再允许脚手架、命令文案、辅助树文件维护第二套不一致层级定义

违规即失败：

- 发现三层以上目录
- 发现 `L4` 或 `L5`
- 发现 `acceptance.yaml` 使用旧 `level`
- 发现旧层级残留在脚手架或 gate 中

---

## 六、节点生命周期

每个正式节点在 `tree_index.yaml` 中通过 `status` 表示生命周期：

- `specified`
- `in_progress`
- `completed`
- `cancelled`
- `deprecated`

### 6.1 `L1_capability`

可长期存在，通常不会频繁归档变动。

### 6.2 `L2_feature`

是稳定业务特性容器。

### 6.3 `L3_story`

是实施、验证、归档、提交的核心对象。

### 6.4 `Task`

不进入 `tree_index.yaml`，通过 `tasks.md` 管理状态。

---

## 七、与命令和流程的衔接

- `/explore`
  - 确认 `L1_capability`、`L2_feature` 与目标 `L3_story`
- `/prd`
  - 创建或更新 `L3_story` 的 `spec.md + acceptance.yaml`
- `/design`
  - 完成 `L3_story` 的 `design.md + tasks.md`
- `/dev`
  - 消费 `tasks.md` 中的 `Task`
- `/verify`
  - 复核 `L3_story` 完成度与测试证据
- `/commit`
  - 提交已完成的 `L3_story`

---

## 八、总结

三层治理模型下，特性树文档的唯一正式结构为：

```text
L1_capability
  └── L2_feature
        └── L3_story
              └── Task（写在 tasks.md / tasks.yaml）
```

四件套服务于 `L1_capability`、`L2_feature` 与 `L3_story`。  
`Task` 是执行层，不再是目录层。
