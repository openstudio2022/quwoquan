# 特性树层级定义与分解规范（三层目录版）

> **权威**：本文档定义仓库唯一正式层级。
>
> - `L1_capability`
> - `L2_feature`
> - `L3_story`
>
> `Task` 继续存在，但不属于目录层级。

---

## 一、核心原则

### 1.1 三层目录模型

| 层级 | 语义 | 是否目录层 | 是否验收主层 |
|------|------|------------|--------------|
| `L1_capability` | 业务能力 / 平台能力 | 是 | 是 |
| `L2_feature` | 稳定业务特性容器 | 是 | 是 |
| `L3_story` | 最小独立交付单元 | 是 | 是 |

### 1.2 Task 的位置

- `Task` 是工程实施动作
- `Task` 只存在于 `tasks.md` / `tasks.yaml`
- `Task` 不再占用目录层

### 1.3 总体原则

- 树层级只表达交付对象，不表达测试层。
- `L2_feature` 只能是稳定特性容器，不能再继续拆出 `subfeature/detail/leaf` 目录。
- `L3_story` 是最小独立交付、独立验收、独立测试映射单元。
- `contract / policy / schema / model / guard / report` 这类技术切面应回收到 `L3_story` 的文档内部，而不是再占目录层。

---

## 二、层级详细定义

### 2.1 `L1_capability`

| 属性 | 定义 |
|------|------|
| 语义 | 长期存在的业务能力或平台能力边界 |
| 目录 | `specs/feature-tree/<l1-name>/` |
| 作用 | 承载能力边界、关键旅程、NFR、发布治理，以及其下 Feature 组织 |

### 2.2 `L2_feature`

| 属性 | 定义 |
|------|------|
| 语义 | 稳定的特性容器，负责把一组相关 Story 聚合在一起 |
| 目录 | `specs/feature-tree/<L1>/<l2-feature>/` |
| 作用 | 承载特性范围、边界、聚合规则、Feature 级设计与验收 |

**判断标准**：

- 是否是一组长期稳定、可承载多个 Story 的业务特性？
- 是否本身更像“主题/模块/能力簇”，而不是一次性交付单元？

**禁止**：

- 用 `L2_feature` 表示单次开发任务
- 在 `L2_feature` 下继续建 `subfeature/detail/leaf`

### 2.3 `L3_story`

| 属性 | 定义 |
|------|------|
| 语义 | 最小独立交付、独立验收、独立测试映射的 Story |
| 目录 | `specs/feature-tree/<L1>/<L2>/<l3-story>/` |
| 作用 | 承载规格、设计、任务、验收和测试证据的主单元 |

**判断标准**：

- 是否可单独描述用户/平台价值？
- 是否可单独写 `acceptance.yaml`？
- 是否可单独判断 done / not done？
- 是否应作为 `/prd`、`/design`、`/dev`、`/verify`、`/commit` 的核心对象？

---

## 三、目录与文档结构

```text
specs/feature-tree/
  <l1-capability>/
    spec.md
    design.md
    tasks.md
    acceptance.yaml
    <l2-feature>/
      spec.md
      design.md
      tasks.md
      acceptance.yaml
      <l3-story>/
        spec.md
        design.md
        tasks.md
        acceptance.yaml
```

---

## 四、分解决策树

```text
需求/问题
   │
   ▼
是否属于既有能力域？
   ├─ 否 → 归属一个 L1_capability
   └─ 是
        │
        ▼
是否是一组长期稳定、可承载多个故事的业务特性？
   ├─ 是 → 建立/归入 L2_feature
   └─ 否 → 归入既有 L2_feature
        │
        ▼
是否可形成独立交付、独立验收、独立测试映射单元？
   ├─ 是 → 建立/归入 L3_story
   └─ 否 → 写入该 Story 的文档内部或任务清单
```

---

## 五、与验收和测试的关系

- 树层级与测试层级彻底解耦。
- 测试统一使用 `T1~T4`。
- `L1_capability`、`L2_feature`、`L3_story` 都可拥有 `acceptance.yaml`。
- `Task` 只通过任务项回链到所属 `L3_story` 的验收项。

---

## 六、门禁与违规规则

以下情况一律视为违规：

- 新增 `subfeature/detail/leaf` 一类额外目录层
- 新建四层以上特性目录
- 将工程任务建成目录层
- 在文档、脚本、索引中继续维护旧层级兼容表

门禁策略：

- 发现旧层级枚举：**FAIL**
- 发现四层以上目录：**FAIL**
- 发现 `acceptance.yaml` 使用旧 `level`：**FAIL**
- 发现脚手架仍产出旧层级：**FAIL**

---

## 七、实施卡点映射

| 阶段 | 作用对象 |
|------|----------|
| `/explore` | 确认 `L1_capability`、`L2_feature` 与目标 `L3_story` |
| `/prd` | 创建或更新 `L3_story` 的 `spec.md + acceptance.yaml` |
| `/design` | 完成 `L3_story` 的 `design.md + Task` 拆解 |
| `/dev` | 逐项执行 `Task` |
| `/verify` | 验证 `L3_story` 完成度与测试证据 |
| `/commit` | 提交已完成的 `L3_story` |

---

## 八、总结

仓库特性树的唯一正式结构为：

```text
L1_capability
  └── L2_feature
        └── L3_story
              └── Task（非目录层）
```
