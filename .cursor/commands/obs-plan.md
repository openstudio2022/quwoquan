---
name: /obs-plan
id: obs-plan
category: Observability
description: 全栈可观测 · 能力演进规划（spec-first + metadata-first + T1-T4 + DDD/端云/存储约束）
---

# obs-plan

## 命令目的
基于 `/obs-audit` 产出的审计报告，生成与 SDD 主流程完全对齐的全栈可观测性演进规划。

## 输入
- `--from {audit|goal|gap}` 规划来源（默认 audit）
- `--priority {p0|p1|p2|all}` 只输出指定优先级
- `--horizon {sprint|quarter|half}` 规划周期

## 与 SDD 主流程的关系

```
/obs-audit → /obs-plan → （用户确认） → /obs-dev
                ↓ 等价于
         /explore → /baseline (或 /prd → /design) → /dev
```

- `/obs-plan` 产出必须可映射到 `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 四件套
- 每个 plan item 实施通过 `/obs-dev`（等价 `/dev`）进入
- 涉及新增 API / 字段 / 错误码 / 路由的 item 必须标注 `metadata-first`

## 规划约束（强制，源自仓库开发规则）

### C1. spec-first + acceptance-first
- 每个 P0/P1 plan item 必须包含验收标准（可映射到 T1~T4）
- 不得只写"实现 XXX"，必须写明验收条件

### C2. metadata-first
- 凡涉及新增字段、API、错误码：`metadata YAML → make verify → make codegen → 业务逻辑 → 测试`
- 标注哪些 item 需要先改 metadata（如 `service.yaml`、`errors.yaml`、`redis_keyspace.yaml`）

### C3. DDD 分层约束
新增可观测性代码的分层要求：

| 层级 | 位置 | 允许 |
|------|------|------|
| 域/运行时 | `runtime/observability/`、`runtime/recommendation/` | 指标定义、度量逻辑（无 DB import） |
| 应用 | `internal/application/` | 行为处理编排 |
| 适配器 | `internal/adapters/http/` | 指标暴露 endpoint |
| 基础设施 | `internal/infrastructure/` | Mongo/Redis/ES 存储实现 |

- 禁止在 runtime / application 层 import 数据库驱动
- 指标计算逻辑必须在 runtime 层（可复用于多个服务）

### C4. 强类型
- 端侧 `TelemetryEvent` 必须强类型（`eventType` 为 enum，`context` 为 typed class，非 Map）
- Go 侧行为/指标结构体无 `interface{}` 传输
- 指标计数器使用 `atomic.Int64`，不用 `interface{}`

### C5. 存储无关
- 新增存储需求先定义 interface（application / domain 层），实现放 infrastructure
- 行为事件存储通过 `EventSink` 接口抽象，可切换 Mongo/Kafka/ClickHouse
- 端侧本地存储通过统一服务层（`TelemetryQueue`），不直接操作 Hive box

### C6. 端云一致
- Dart `TelemetryEvent` schema ↔ Go 接收 API 的 request body schema
- 行为 action 枚举值端云相同字符串常量
- 端侧 `pageId` / `surfaceId` 来自 codegen `AppRoutePaths`
- Go 侧 `surfaceId` 验证与 `ui_config.yaml` 对齐

### C7. 四层测试
每个 plan item 标注测试层：

| 层 | 可观测域对应 | 要求 |
|----|-----------|------|
| T1 | `*_test.go` / `*_test.dart` | 每个 public func |
| T2 | `verify_telemetry_coverage.py` / contract test | schema 对齐 + 页面覆盖 |
| T3 | 端云联调（POST 行为事件 → Go 接收解析） | 真实 HTTP |
| T4 | Patrol 旅程（真机操作 → 验证事件上报） | 真机 |

## 规划维度（8 层）

### L1. 统一埋点 SDK 架构
**三层 SDK**（L3 业务语义 → L2 统一事件总线 → L1 可靠传输）
- 统一事件 schema（行为/体验/异常/性能四类）
- 自动附加 context（session/page/experiment/referral）
- **强类型**：`eventType` 为 enum，`context` 为 typed class
- **metadata 驱动**：`pageId` / `surfaceId` 来自 codegen

### L2. 存储架构演进
**高性价比分层**（热 Redis → 温 Mongo → 冷 S3）
- **存储无关**：所有存储通过 interface 抽象
- **DDD**：interface 定义在 application 层，实现在 infrastructure 层

### L3. 性能监控体系
- 端侧冷启动/TTI/帧率/API 耗时
- 云侧 HTTP histogram / DB 延迟 / 管线延迟
- **强类型**：计时指标使用 `time.Duration` / `Duration`，非 `int` 毫秒

### L4. 页面全覆盖方案
- GoRouter Observer 自动埋点（零代码接入 56 页面基础曝光/停留）
- 分 4 批深度接入
- **metadata 驱动**：pageId 自动从 `AppRoutePaths` 获取

### L5. 指标体系建设
- 黄金指标（DAU/PV/CTR/深度率/错误率/P99）
- 二层指标（按类型/来源/实验桶/时段切分）
- **存储无关**：Redis 实时 → Mongo 聚合 → S3+DuckDB 离线

### L6. 数据回流推荐系统
- 行为 → HotPath → tag 加权（实时）
- 行为 → 冷存 → 训练样本（小时级）
- **端云一致**：新增行为字段必须同步 Dart ↔ Go ↔ YAML

### L7. 生命周期管理
- 媒体文件、行为数据、端侧缓存的 TTL/归档/清理策略
- **存储无关**：通过 lifecycle policy interface 抽象

### L8. 公共统一埋点规范
- 自动埋点（Router observer / lifecycle observer / HTTP 拦截器 / error handler）
- 无需业务代码即可覆盖基础维度

## 输出格式

```
╔══════════════════════════════════════════════════╗
║   全栈可观测性演进规划（/obs-plan）                ║
╠══════════════════════════════════════════════════╣
║ P0 阻塞修复                                       ║
║   [OBS-P0-001] 标题                               ║
║     层: L? | metadata: Y/N | 验收: ...            ║
║     测试: T1 ☐ T2 ☐ T3 ☐ T4 ☐                   ║
║     DDD: 域→应用→适配→基础设施 分层说明           ║
║     强类型: typed enum/class, 无 Map/interface{}  ║
║     存储无关: interface 在上层, 实现在 infra      ║
║     端云: Dart schema ↔ Go schema 对齐说明       ║
║     影响文件: ...                                  ║
║     工作量: ...                                    ║
╠══════════════════════════════════════════════════╣
║ P1/P2/P3 同上格式                                 ║
╚══════════════════════════════════════════════════╝
```

## 规划→实施衔接
- P0/P1 `metadata-first` 标注的 item 必须先完成 metadata 变更
- 用户确认后通过 `/obs-dev` 进入实施
- `/obs-dev` 内部遵循 `/dev` 的完整闭环
