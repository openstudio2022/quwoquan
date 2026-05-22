---
name: /obs
id: obs
category: Observability
description: 全栈可观测 · 统一入口（六专家视角 + DevOps 合规 + SDD 主流程对齐）
---

# obs

## 命令目的
全栈可观测性体系的统一入口。默认先执行 9 维审计（7 功能 + 2 合规），再生成与 SDD 主流程对齐的修复规划。

## 输入
- `--mode {inspect|plan|dev|full}` 运行模式（默认 inspect）
  - `inspect`：审计 → 产出断点报告 → 自动生成修复规划
  - `plan`：跳过审计，直接基于目标生成规划
  - `dev`：进入实施（等价 `/dev`，强制闭环）
  - `full`：完整流程（审计 → 规划 → 确认后实施）
- `--scope {all|telemetry|storage|performance|coverage|metrics|compliance}` 聚焦范围

## 默认行为（`/obs` 无参数）

```
Step 1: 九维审计（/obs-audit --scope all）
    ↓   含 D8 DDD/强类型/存储无关合规
    ↓   含 D9 四层测试/特性树合规
Step 2: 页面覆盖矩阵（56 页面 × 7 维度）
    ↓
Step 3: 断点识别与优先级排序
    ↓   合规 BLOCKING 项触发 GATE_BLOCK
Step 4: 规划（/obs-plan --from audit）
    ↓   每个 item 标注 metadata/DDD/类型/存储/端云/T1-T4
Step 5: 输出结论与下一步建议
```

## 六专家角色定义

### 1. 推荐搜索算法专家
行为数据回流推荐/搜索完整性

### 2. 健康监测质量专家
异常捕获 → 上报 → 追溯闭环

### 3. 运营专家
指标实时性 + AB 实验 + 旅程还原

### 4. 系统应用架构师
存储分层 + 弹性 + 网络鲁棒性

### 5. 产品总监
页面全覆盖 + 漏斗可度量 + 异常可发现

### 6. 代码评审专家
**确保可观测性体系遵循仓库全局工程规范**：

| 约束 | 检查内容 | 对应规则 |
|------|----------|---------|
| **DDD 分层** | runtime 无 DB import；infrastructure 可替换 | `01-arch-constraints §1.2` |
| **强类型** | 无 `interface{}` / `Map<String, dynamic>` / `dynamic` 穿透 | `01-arch-constraints §2.4` |
| **存储无关** | Repository / EventSink 是 interface | `01-arch-constraints §1.3` |
| **端云一致** | Dart DTO ↔ Go struct ↔ YAML 字段对齐 | `01-arch-constraints §3.1` |
| **元数据驱动** | pageId/surfaceId/path/errorCode 来自 codegen | `01-arch-constraints §3.2` |
| **codegen 保护** | `DO NOT EDIT` 文件无手改 | `01-arch-constraints §1.5` |
| **四层测试** | T1 单元 / T2 契约 / T3 联调 / T4 旅程 | `/dev` G2 |
| **特性树** | 四件套齐全 | `00-fullstack-development-flow` |
| **Mock 隔离** | UI 不 import mock 目录 | `08-mock-data-isolation` |
| **错误码** | errors.yaml → codegen → 业务代码 | `01-arch-constraints §3.3` |
| **页面矩阵** | 新增页面更新横向质量矩阵 | `09-page-horizontal-quality` |
| **环境包** | 生产包默认 Remote，无 Mock 入口 | `08-mock-data-isolation` 发布态 |

## 端到端数据流（含合规检查点）

```
┌─────────────────────────────────────────────────────────────────┐
│ 端侧                                                            │
│  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 自动埋点 │  │ 行为 SDK  │  │ 性能 SDK │  │ 异常捕获链    │  │
│  │ (Router  │  │(Engagement│  │(TTI/Jank │  │(Zone/Flutter │  │
│  │ Observer)│  │ Tracker)  │  │/API Time)│  │ Error/Platform)│ │
│  └─[meta]──┘  └─[typed]──┘  └─[typed]──┘  └──[typed]─────┘  │
│   pageId from       ↑              ↑               ↑            │
│   codegen      强类型 DTO     Duration 类型     结构化错误       │
│                      ▼                                           │
│              ┌───────────────┐                                   │
│              │ TelemetryService│ ← 强类型 event schema          │
│              │ (统一总线)      │ ← 不操作 Map<String,dynamic>   │
│              └───────┬───────┘                                   │
│                      ▼                                           │
│              ┌───────────────┐                                   │
│              │ BatchUploader  │ ← 统一传输层                     │
│              │ (缓冲/gzip)   │ ← Hive 通过 TelemetryQueue      │
│              └───────┬───────┘    (不直接操作 box)               │
└──────────────────────┼──────────────────────────────────────────┘
                       │ HTTP POST (batch, gzip)
                       │ ← 端云字段一一对齐（verify_feature_consistency）
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 云侧                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │Ingest API│   │ Behavior │   │ Feature  │   │  Metrics     │ │
│  │[adapters]│──→│ Service  │──→│ Projector│──→│ [runtime]    │ │
│  │  ↑meta   │   │[applicat]│   │[applicat]│   │  无DB import │ │
│  └──────────┘   └────┬─────┘   └──────────┘   └──────────────┘ │
│                      │                                           │
│          ┌───────────┼───────────┐                               │
│          ▼           ▼           ▼                               │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                       │
│   │ Redis    │ │ MongoDB  │ │ S3       │  ← 全部通过 interface │
│   │[infrastr]│ │[infrastr]│ │[infrastr]│  ← 存储无关           │
│   └──────────┘ └──────────┘ └──────────┘                       │
│                                                                  │
│   ┌──────────────────────────────────────┐                      │
│   │         数据消费层                    │                      │
│   │  推荐引擎 / AB / 训练 / 大盘 / 告警  │                      │
│   └──────────────────────────────────────┘                      │
│                                                                  │
│   ┌──────────────────────────────────────┐                      │
│   │         合规检查点                    │                      │
│   │  DDD ✓ 强类型 ✓ 存储无关 ✓ 端云 ✓   │                      │
│   │  metadata ✓ T1-T4 ✓ Mock隔离 ✓      │                      │
│   └──────────────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────────┘
```

## 输出要求

1. **当前水位摘要**：可观测性体系成熟度
2. **页面覆盖矩阵**：56 页面 × 7 维度
3. **断点清单**：功能断点 + 合规违规，标明优先级/文件/规则引用
4. **修复规划**：P0-P3 条目，每个标注 metadata/DDD/类型/存储/端云/T1-T4
5. **下一步**：明确命令和参数

## 命令家族

```
/obs (统一入口)
├── /obs-audit  (九维审计 = 7 功能 + 2 合规)
├── /obs-plan   (规划，含 C1-C7 约束)
└── /obs-dev    (实施，等价 /dev 完整闭环)
         ↓
    /commit → /deploy (与主流程共用)
```

## 与 rec-* 的协同

| 场景 | 用 |
|------|-----|
| 推荐链路功能+合规 | `/rec` |
| 可观测体系功能+合规 | `/obs` |
| 完整（含推荐回流） | `/obs --mode full` + `/rec-audit --scope compliance` |
| 修复推荐行为断点 | `/rec-dev` |
| 修复埋点/存储/性能断点 | `/obs-dev` |
| 日常合规检查 | `/audit`（代码库级） |
