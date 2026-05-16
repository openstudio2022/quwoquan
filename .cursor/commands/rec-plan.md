---
name: /rec-plan
id: rec-plan
category: Recommendation
description: 推荐系统 · 能力演进规划（spec-first + metadata-first + T1-T4 证据矩阵）
---

# rec-plan

## 命令目的
基于 `/rec-audit` 自检报告或用户指定目标，生成与 SDD 主流程对齐的推荐系统能力演进规划。每个 plan item 必须满足 spec-first、metadata-first、四层测试和端云一致要求。

## 输入
- `--from {audit|goal|gap}` 规划来源（默认 audit）
- `--priority {p0|p1|p2|p3|all}` 只输出指定优先级
- `--horizon {sprint|quarter|half}` 规划周期

## 与 SDD 主流程的关系

```
/rec-audit → /rec-plan → （用户确认） → /rec-dev
                ↓ 等价于
         /explore → /baseline (或 /prd → /design) → /dev
```

- `/rec-plan` 产出的规划**必须**可以映射到 SDD 主流程中的 `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 四件套
- 每个 plan item 的实施**必须**通过 `/rec-dev`（等价于 `/dev`）进入，不允许跳过设计直接编码
- 涉及新增 API / 字段 / 错误码 / 路由的 plan item 必须标注 `metadata-first`

## 规划约束（强制，源自开发流程规则）

### C1. spec-first + acceptance-first
- 每个 P0/P1 plan item 必须包含：验收标准（可映射到 T1~T4）
- 规划不得只写"实现 XXX 功能"，必须写明验收条件（如"RuleScorer 新增 entityAffinity 维度，T1 断言 score > baseline"）

### C2. metadata-first
- 凡涉及新增字段、API、错误码：顺序固定为 `metadata YAML → make verify → make codegen → 业务逻辑 → 测试`
- 规划中必须标注哪些 item 需要先改 metadata（如 `feature_registry.yaml`、`service.yaml`、`errors.yaml`）

### C3. DDD 分层约束
- 新增推荐域代码必须遵循分层：
  - `runtime/recommendation/`：推荐域核心逻辑（等价于 domain + application）
  - `services/content-service/internal/infrastructure/recommendation/`：存储实现
  - `services/content-service/internal/adapters/http/`：HTTP 暴露
- 禁止在 `runtime/recommendation/` 中 import 数据库驱动

### C4. 强类型
- 所有推荐特征必须在 `UserFeatureVector` / `ContentCandidate` 中有强类型字段
- 禁止 `interface{}` 作为特征传输
- Dart 端 DTO 必须强类型（`PostBaseDto` 子类或 ViewModel），禁止 UI 层直接操作 `Map<String, dynamic>`

### C5. 存储无关
- 新增存储需求必须先定义 interface（在 application / domain 层）
- 实现放在 infrastructure 层
- 切换存储引擎只需替换 infrastructure 实现 + 依赖注入

### C6. 端云一致
- Dart `BehaviorEvent` 字段 ↔ Go `BehaviorSignal` 字段 ↔ `feature_registry.yaml` 必须一一对齐
- 新增枚举值（如 `ReferralSource`）必须端云同步、使用相同字符串常量
- Go struct 的序列化 tag 必须与 Dart `toJson` 的 key 一致

### C7. 四层测试
每个 plan item 必须标注对应测试层：

| 测试层 | 推荐域对应 | 要求 |
|--------|-----------|------|
| T1 | `engine_test.go` / `*_test.go` 单元 | 每个 public func |
| T2 | 契约测试 / `verify_feature_consistency.py` | 端云 schema 对齐 |
| T3 | `behavior_repository_contract_test.dart` / 端云联调 | 真实 HTTP + JSON |
| T4 | Patrol 真机旅程 | 推荐 feed 核心路径 |

## 规划维度（6 层）

### L1. 数据工程 → 推荐管线
（保持不变）

### L2. 行为采集与来源追踪
（保持不变）

### L3. 特征工程全景
（保持不变）

### L4. 算法能力演进
（保持不变）

### L5. 社交与实体深度利用
（保持不变）

### L6. 指标体系与实验平台
（保持不变）

## 输出格式

```
╔══════════════════════════════════════════════════╗
║       推荐系统能力演进规划（/rec-plan）             ║
╠══════════════════════════════════════════════════╣
║ 目标基线 / 对标差距 / 当前水位                     ║
╠══════════════════════════════════════════════════╣
║ P0 阻塞修复                                       ║
║   [REC-P0-001] 标题                               ║
║     层: L? | metadata: Y/N | 验收: ...            ║
║     测试: T1 ☐ T2 ☐ T3 ☐ T4 ☐                   ║
║     DDD: runtime/recommendation/ → infra/rec/    ║
║     端云: BehaviorEvent ↔ BehaviorSignal ↔ YAML  ║
║     影响文件: ...                                  ║
║     工作量: ...                                    ║
╠══════════════════════════════════════════════════╣
║ P1/P2/P3 同上格式                                 ║
╚══════════════════════════════════════════════════╝
```

## 规划→实施衔接

- P0/P1 项的 `metadata-first` 标注的 item 必须先完成 metadata 变更
- 用户确认后通过 `/rec-dev` 进入实施
- `/rec-dev` 内部遵循 `/dev` 的完整执行闭环（plan mode → Red→Green→Refactor → gate → archive）
