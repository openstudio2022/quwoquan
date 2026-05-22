---
name: /rec
id: rec
category: Recommendation
description: 推荐系统 · 统一入口（默认先自检再规划，四专家 + DevOps 合规）
---

# rec

## 命令目的
推荐系统能力的统一入口。默认先自检断点和合规性，再生成修复规划。与 SDD 主流程（spec-first / metadata-first / acceptance-first / T1-T4）完全对齐。

## 输入
- `--mode {inspect|plan|dev|bench|full}` 运行模式（默认 inspect）
  - `inspect`：运行 `/rec-audit`（含 D9 DDD/类型/存储合规 + D10 测试/特性树合规），产出修复规划
  - `plan`：跳过自检，直接基于用户目标生成规划
  - `dev`：进入实施（等价 `/dev`，强制闭环）
  - `bench`：运行 `/rec-bench` 业界对标评估
  - `full`：完整流程（audit → bench → plan），最全面
- `--scope {all|behavior|feature|recall|scoring|social|pipeline|metrics|compliance}` 聚焦范围
- `--benchmark {tiktok|xiaohongshu|wechat|all}` 对标对象

## 默认行为（`/rec` 无参数）

```
Step 1: 十维自检（/rec-audit --scope all）
    ↓   含 D9 DDD/强类型/存储无关合规
    ↓   含 D10 四层测试/特性树合规
Step 2: 对标差距摘要
    ↓
Step 3: 规划（/rec-plan --from audit）
    ↓   每个 item 标注 metadata-first / T1-T4 / DDD 层
Step 4: 输出结论与下一步建议
```

## 四专家角色定义

### 推荐算法专家
- 行为→特征→模型→打分→重排全链路
- 标签体系更新时算法自动同步
- TypePreference 去偏差（ENER）
- 社交信号参与排序和召回

### 数据工程师
- feature_registry.yaml ↔ Go ↔ Python 一致性
- release manifest → bulk import → feature store 贯通
- 离线训练管线可用性

### 推荐运营总监
- 指标实时性和可切分性
- AB 实验正交分层
- 冷启动效率和长期健康

### 代码评审专家
**该角色确保推荐系统遵循仓库全局的工程规范**：

| 约束 | 检查内容 | 对应规则 |
|------|----------|---------|
| DDD 分层 | domain 不 import infrastructure | `01-arch-constraints §1.2` |
| 强类型 | 无 `interface{}` / `Map<String, dynamic>` 穿透 | `01-arch-constraints §2.4` |
| 存储无关 | Repository 是 interface，infrastructure 可替换 | `01-arch-constraints §1.3` |
| 端云一致 | Dart DTO ↔ Go struct ↔ metadata YAML | `01-arch-constraints §3.1` |
| 元数据驱动 | path/operation/error_code 来自 codegen | `01-arch-constraints §3.2` |
| codegen 保护 | `DO NOT EDIT` 文件无手改 | `01-arch-constraints §1.5` |
| 四层测试 | T1 单元 / T2 契约 / T3 联调 / T4 旅程 | `/dev` G2 |
| 特性树 | 四件套齐全（spec/acceptance/design/plan） | `00-fullstack-development-flow` |
| Mock 隔离 | UI 不 import mock 目录 | `08-mock-data-isolation` |
| 错误码 metadata | errors.yaml → codegen → 业务代码 | `01-arch-constraints §3.3` |

## 断点检查链路图

```
数据工程                    行为采集                   特征工程
┌──────────┐              ┌──────────┐              ┌──────────┐
│ tags/    │──taxonomy──→ │ tag索引  │──real-time─→ │ 四维亲和  │
│ entities/│──bulk───────→│ entity索引│──propagate─→│ 实体亲和  │
│ content/ │──release────→│ 候选池   │──feature──→ │ 候选特征  │
└──────────┘              └──────────┘              └──────────┘
     ↑                         ↑                         ↑
 metadata-first           端云一致                    强类型
 (schema → codegen)      (Dart↔Go↔YAML)            (typed struct)

用户行为                                                  │
┌──────────┐                                             ↓
│ 端侧SDK  │──event──→ API ──→ HotPath ──→ 投影 ──→ 用户画像
│ tracker  │         │         │              │
│ (typed   │         │     tag加权            │      ┌──────────┐
│  DTO,    │         │    (depth×source)      └────→ │ 特征库   │
│  no Map) │         │                               │(interface)│
└──────────┘         │                               └────┬─────┘
     ↑               └─ feedRequestId ───────────────────┘
 端云一致                                                  │
 (BehaviorEvent ↔ BehaviorSignal)                         │
                                                          │
召回层           排序层            重排层           合规层  │
┌────────┐     ┌────────┐      ┌────────┐      ┌────────┐│
│ Tag    │     │ Rule   │      │ 多样性  │      │ DDD    ││
│ Hot    │────→│ Model  │─────→│ 反茧房  │─────→│ T1-T4  ││
│ Social │     │(cascade│      │ 冷启动  │      │ 端云一致││
│ Vector │     │ typed) │      │ ENER   │      │ 存储无关││
│ Entity │     │        │      │ 作者去重│      │ 强类型  ││
└────────┘     └────────┘      └────────┘      └────────┘│
     ↑              ↑                                     │
 存储无关        无 interface{}     feature vector ────────┘
 (interface)   (UserFeatureVector)
```

## 命令家族关系

```
/rec (统一入口)
├── /rec-audit  (十维自检 = 8 业务 + 2 合规)
├── /rec-bench  (业界对标)
├── /rec-plan   (规划，含 C1-C7 约束)
└── /rec-dev    (实施，等价 /dev 闭环)
         ↓
    /commit → /deploy (与主流程共用)
```
