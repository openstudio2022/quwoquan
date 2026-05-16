---
name: /obs-audit
id: obs-audit
category: Observability
description: 全栈可观测 · 端到端自检审计（埋点/存储/性能/页面/指标 + DDD/端云/类型/测试合规）
---

# obs-audit

## 命令目的
以推荐搜索算法专家、健康监测质量专家、运营专家、系统应用架构师、产品总监和**代码评审专家**六重视角，对全应用可观测性体系做端到端自检审计。既识别功能缺口，也审计 DDD、强类型、存储无关、端云一致、元数据驱动和四层测试的合规性。

## 输入
- `--scope {all|telemetry|storage|performance|coverage|metrics|compliance}` 审计范围（默认 all）
- `--depth {quick|standard|deep}` 审计深度（默认 standard）

## 六重专家视角

### 视角一：推荐搜索算法专家
- 行为数据能否回流到特征工程
- 采集粒度是否足以支撑多目标排序
- 搜索行为是否被捕获并反哺搜索排序

### 视角二：健康监测质量专家
- 端侧异常捕获链完整性
- 异常遥测上报可靠性
- 云侧错误率/延迟的可观测覆盖

### 视角三：运营专家
- 黄金指标实时可观测
- 用户旅程还原能力
- AB 实验数据管线完整性

### 视角四：系统应用架构师
- 存储选型合理性和分层策略
- 存储无关抽象层的覆盖
- 网络层统一性

### 视角五：产品总监
- 所有用户触达页面是否可追踪
- 关键转化漏斗每步可度量
- 异常体验自动发现

### 视角六：代码评审专家（DevOps 合规）
- **DDD 分层**：遥测/埋点/存储相关代码是否遵循 `domain ← application ← adapters ← infrastructure` 单向依赖
- **强类型**：
  - 端侧 `TelemetryEvent` / `BehaviorEvent` 是否全部强类型字段
  - 禁止 UI/Provider 层直接操作 `Map<String, dynamic>` 构造事件
  - Go 侧行为/指标结构体无 `interface{}` 传输
- **存储无关**：
  - 行为事件存储是否通过 interface 抽象（`BehaviorEventStore`）
  - 特征库是否通过 interface 抽象（`FeatureStore`）
  - 切换 Mongo → ClickHouse / Kafka 只需替换 infrastructure 实现
  - 端侧本地存储（Hive/SharedPreferences/sqflite）是否有统一服务层
- **端云一致**：
  - Dart `BehaviorEvent` ↔ Go `BehaviorSignal` ↔ `feature_registry.yaml` 字段一一对齐
  - 行为 action 枚举值端云使用相同字符串常量
  - 错误码走 `errors.yaml` → codegen，禁止硬编码
- **元数据驱动**：
  - 页面 `surfaceId` / `pageId` 来自 `app_route_paths.g.dart`（codegen）
  - 行为 API path 来自 `service.yaml` codegen
  - 指标 endpoint 路径来自统一注册
- **四层测试**：
  - T1：单元测试覆盖所有 public func
  - T2：契约测试（Dart behavior contract / Go endpoint contract）
  - T3：端云联调（真实 HTTP POST 行为上报 → 真实接收解析）
  - T4：Patrol 旅程（真机触发行为 → 验证上报）
- **特性树对齐**：
  - 可观测性能力是否归属到 `L1_capability`
  - 是否有 `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 四件套
- **codegen 保护**：`DO NOT EDIT` 文件无手改
- **Mock 隔离**：UI 层不 import `cloud/services/*/mock/`，遵循 `08-mock-data-isolation`

## 审计维度（9 维）

### D1. 埋点采集完整性
（行为/体验/异常/性能四类埋点逐页验证）

### D2. 上报链路与可靠性
（多通道合并 / 缓冲 / 重试 / 持久化 / flush 策略）

### D3. 存储架构审计
（云侧 Mongo/PG/Redis/S3/CDN + 端侧 Hive/SharedPreferences/sqflite）

### D4. 性能断点识别
（端侧冷启动/TTI/帧率/API 耗时 + 云侧管线/DB/下游延迟）

### D5. 页面覆盖矩阵
56 页面 × 7 维度（曝光/停留/深度/来源/互动/异常/性能）

### D6. 指标体系审计
（黄金指标 + 二层指标 + 技术指标完整性）

### D7. 用户旅程深度关联
（session → page_view → action → outcome 四层关联）

### D8. DDD / 强类型 / 存储无关合规
扫描代码库中遥测和存储相关文件：

| 检查项 | 扫描范围 | 合格标准 |
|--------|---------|---------|
| DDD import | `runtime/`、`internal/application/`、`internal/domain/` | 无跨层 DB driver import |
| 强类型 | `BehaviorEvent`、`BehaviorSignal`、`UserFeatureVector` | 无 `interface{}` / `dynamic` |
| 存储 interface | `BehaviorEventStore`、`FeatureStore`、`BulkImportStore` | 均为 interface 定义 |
| 端云字段 | Dart DTO ↔ Go struct ↔ YAML | `verify_feature_consistency.py` 通过 |
| metadata path | 行为 API endpoint | 来自 codegen，非硬编码 |
| codegen 保护 | `*.g.dart`、`*.g.go` | 无手改 |
| Mock 隔离 | `lib/ui/**` | 不 import `cloud/services/*/mock/` |

### D9. 四层测试与特性树合规

| 检查项 | 合格标准 |
|--------|---------|
| T1 覆盖 | `*_test.go` / `*_test.dart` 覆盖新增 public func |
| T2 覆盖 | 契约测试存在且与 schema 对齐 |
| T3 覆盖 | 端云联调测试存在（真实 HTTP + JSON） |
| T4 覆盖 | Patrol 核心旅程存在 |
| 特性树 | `L1/L2/L3` 归属明确 |
| 四件套 | `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 齐全 |
| acceptance | 无 `pending` 验收项 |
| CR | delta 与影响已记录 |

## 输出格式

```
╔══════════════════════════════════════════════════════╗
║   全栈可观测性审计报告（/obs-audit）                    ║
╠══════════════════════════════════════════════════════╣
║ D1. 埋点采集完整性    ✓/○/✗  (N/M 页面已覆盖)        ║
║ D2. 上报链路可靠性    ✓/○/✗  (N 条链路/N 条断点)      ║
║ D3. 存储架构健康度    ✓/○/✗  (N 个存储/N 个缺口)      ║
║ D4. 性能断点          ✓/○/✗  (N 个识别)               ║
║ D5. 页面覆盖矩阵      ✓/○/✗  (N/56 页面满覆盖)       ║
║ D6. 指标体系完整度    ✓/○/✗  (N/M 指标可采集)         ║
║ D7. 旅程关联深度      ✓/○/✗  (N/4 层)                ║
║ D8. DDD/类型/存储合规  ✓/○/✗  (N 项违规)              ║
║ D9. 测试与特性树       ✓/○/✗  (N 项缺失)              ║
╠══════════════════════════════════════════════════════╣
║ 断点清单                                               ║
║   P0(BLOCKING): N 项  P1: N 项  P2: N 项  P3: N 项   ║
╚══════════════════════════════════════════════════════╝
```

每个 ✗ 项附带：文件路径 + 描述 + 修复方案 + 对应规则引用

## 后续动作
- D8/D9 的 BLOCKING 项必须标注 `GATE_BLOCK`，不允许绕过
- 完成后自动生成 `/obs-plan` 输入
