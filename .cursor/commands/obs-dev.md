---
name: /obs-dev
id: obs-dev
category: Observability
description: 全栈可观测 · 实施开发（等价 /dev，强制 DDD/metadata/T1-T4/端云一致/存储无关闭环）
---

# obs-dev

## 命令目的
按 `/obs-plan` 规划执行可观测性体系的实际开发。执行姿态与 `/dev` 完全等价。

## 输入
- `--plan {planFile}` 指定规划文件
- `--items {OBS-P0-001,...}` 指定实施条目
- `--scope {telemetry|storage|performance|coverage|metrics}` 范围

## Dev Gate（等价 `/dev` 前置条件）

进入 `/obs-dev` 前必须确认：
- `/obs-plan` 已完成且确认
- 涉及 metadata 变更的 item 已标注
- 验收标准已定义且可映射 T1~T4
- 可观测性功能归属 `L1/L2/L3` 已明确

任一未满足：`GATE_BLOCK`

## 执行姿态（与 /dev 完全对齐）

**必须先进入任务级 plan mode**：

1. 通读 `/obs-plan` 目标 item 的验收、DDD 约束、端云对齐要求
2. 审视 metadata/codegen、前后端影响面、测试层覆盖
3. 若发现缺口，先自动修复再继续
4. 派生会话 todo

**禁止**：
- 跳过 metadata 直接手写 DTO / struct / API path
- 用 `interface{}` / `Map<String, dynamic>` / `dynamic` 传递事件字段
- 在 runtime/domain 层 import 数据库驱动
- 端云字段不对齐就继续
- 不写测试宣布完成
- `DO NOT EDIT` 文件手改
- UI 层 import `cloud/services/*/mock/`

## 实施顺序（强制）

```
1. metadata YAML    — service.yaml / errors.yaml / redis_keyspace.yaml / ui_config.yaml
2. make verify      — make -C quwoquan_service verify-metadata
3. make codegen     — make codegen && make codegen-app（含 AppRoutePaths 等）
4. domain/runtime   — runtime/observability/ 纯逻辑（metrics 定义、计算、度量）
5. infrastructure   — infrastructure/（Mongo/Redis/ES 存储实现 + TTL）
6. application      — application/（行为处理编排、投影器组装）
7. adapters/http    — adapters/http/（指标暴露 endpoint、行为接收 API）
8. dart transport   — lib/core/telemetry/（统一 SDK + BatchUploader）
9. dart cloud       — lib/cloud/services/behavior/（端云对接）
10. dart ui         — lib/ui/**/pages/（页面接入 + Router observer）
11. test            — T1 → T2 → T3 → T4（按层递进）
```

## DDD 分层检查清单

```
☐ 指标定义/计算在 runtime/（无 DB import）
☐ 存储实现在 infrastructure/（interface 定义在上层）
☐ HTTP 暴露在 adapters/http/
☐ application 层只做编排
☐ domain → application → adapters → infrastructure 单向依赖
☐ 端侧：telemetry SDK（core 层）不 import UI 层
☐ 端侧：UI 层通过 Provider 消费 tracker，不直接 new
```

## 强类型检查清单

```
☐ Go: 新增行为/指标结构体字段为具体类型（非 interface{}）
☐ Go: atomic 计数器使用 atomic.Int64（非 interface{}）
☐ Go: 时间度量使用 time.Duration
☐ Dart: TelemetryEvent eventType 为 enum
☐ Dart: TelemetryEvent context 为 typed class（非 Map）
☐ Dart: BehaviorEvent 新增字段为具体 Dart 类型
☐ Dart: UI/Provider 不操作 Map<String, dynamic> 构造事件
☐ 枚举值端云统一（Dart enum string ↔ Go const string）
```

## 存储无关检查清单

```
☐ BehaviorEventStore 是 interface
☐ FeatureStore 是 interface
☐ MetricsStore / EventSink 是 interface（如新增）
☐ 端侧 TelemetryQueue 统一管理（不直接操作 Hive box）
☐ 切换存储只需替换 infrastructure 实现 + DI
☐ 端侧 SharedPreferences 通过 AppPreferencesService 统一
```

## 端云一致检查清单

```
☐ Dart TelemetryEvent schema ↔ Go 接收 API request body
☐ Dart BehaviorEvent 字段集 ⊇ Go BehaviorSignal 字段集
☐ 行为 action 枚举端云字符串常量一致
☐ 端侧 pageId 来自 codegen AppRoutePaths
☐ Go 侧 surfaceId 验证与 ui_config.yaml 对齐
☐ 错误码走 errors.yaml → codegen
☐ verify_feature_consistency.py 通过
```

## 四层测试检查清单

```
☐ T1: 每个新增 public func 有 *_test.go / *_test.dart
☐ T1: metrics 计数逻辑有单元测试
☐ T2: 端云 schema 契约测试
☐ T2: 页面覆盖扫描脚本（verify_telemetry_coverage.py）
☐ T2: make test-contract 通过
☐ T3: 端云联调（真实 POST → 真实接收解析）
☐ T4: Patrol 核心旅程（触发行为 → 验证上报）
```

## Mock / Remote 隔离（与 08-mock-data-isolation 对齐）

```
☐ UI 层不 import cloud/services/*/mock/
☐ Mock 数据仅在 Mock*Repository 或 test/
☐ Remote 实现使用 CloudRuntimeConfig + CloudRequestHeaders
☐ alpha mock 数据来自 contracts/metadata/**/test_fixtures
☐ 新增 Repository → app_providers.dart 注册 Provider
```

## 推荐交叉 Checklist（可观测 × 推荐联动）

```
☐ 新增行为事件类型 → 已同步 rec-audit D2 的 supportedBehaviorActions
☐ 新增行为字段 → 已同步 BehaviorSignal → HotPath → 投影器 → 特征库
☐ 新增指标维度 → 推荐 AB 实验可按该维度切分
☐ 新增页面埋点 → referralSource 已传入（非 default）
☐ 端侧性能打点 → CloudHttpClient 拦截器已覆盖推荐 API
```

## 验证门禁（必须全部通过）

```bash
# Go 编译
cd quwoquan_service && go build ./...

# Go 单元测试（T1）
cd quwoquan_service && go test ./runtime/recommendation/... ./runtime/observability/... -v -count=1

# 特征一致性（T2）
cd quwoquan_service && python3 scripts/ml/verify_feature_consistency.py

# 端侧分析
cd quwoquan_app && dart analyze

# 端侧契约测试（T2）
cd quwoquan_app && flutter test test/cloud/behavior/ test/cloud/content/

# DDD 合规扫描
cd quwoquan_service && python3 -c "
import pathlib
violations = []
for d in ['runtime/recommendation', 'runtime/observability']:
    p = pathlib.Path(d)
    if not p.exists(): continue
    for f in p.rglob('*.go'):
        content = f.read_text()
        for banned in ['go.mongodb.org', 'github.com/go-redis', 'database/sql']:
            if banned in content:
                violations.append(f'DDD_VIOLATION: {f} imports {banned}')
if violations:
    for v in violations: print(f'✗ {v}')
    exit(1)
else:
    print('✓ DDD runtime layers: PASS')
"

# Mock 隔离
make verify-app-mock-isolation

# 页面横向质量
make verify-app-page-horizontal-quality

# 全量门禁
make gate-full
```

## 收口（与 /dev 完全对齐）

所有 item 完成后：
1. 回填 `acceptance.yaml` / `plan.yaml` / `CR` 的 tests/evidence/status
2. 执行 `make gate-full`，无 BLOCKING
3. 自动执行 archive 等价回写
4. 输出完成报告，等待 `/commit`

```text
可观测性实施、验证与归档完成：observability-<scope>
items 完成：N/N
DDD 合规: PASS
端云一致: PASS
强类型: PASS
存储无关: PASS
T1~T4: T1 ✓ T2 ✓ T3 ○ T4 ○
Mock 隔离: PASS
verify: PASS
archive: DONE
下一步：/commit
```

## 与其他命令的关系

| 命令 | 角色 | 等价于 |
|------|------|--------|
| `/obs-audit` | 自检评审 | `/explore` 的可观测专项 |
| `/obs-plan` | 能力规划 | `/baseline` 或 `/prd`+`/design` |
| `/obs-dev` | 实施开发 | **`/dev`**（完整闭环） |
| `/obs` | 统一入口 | 流程编排 |
| `/commit` | 提交 | 与主流程共用 |
| `/verify` | 独立复核 | 与主流程共用 |
