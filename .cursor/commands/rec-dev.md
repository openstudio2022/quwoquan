---
name: /rec-dev
id: rec-dev
category: Recommendation
description: 推荐系统 · 实施开发（等价 /dev，强制 DDD/metadata/T1-T4/端云一致/存储无关闭环）
---

# rec-dev

## 命令目的
按 `/rec-plan` 产出的规划执行推荐系统的实际开发工作。执行姿态与 `/dev` 完全等价：先 plan mode 审视，再自主闭环到可归档、待 `/commit` 状态。

## 输入
- `--plan {planFile}` 指定 `.cursor/plans/` 下的规划文件
- `--items {REC-P0-001,REC-P1-002}` 指定实施条目
- `--scope {behavior|feature|recall|scoring|social|pipeline|metrics}` 范围

## Dev Gate（等价 `/dev` 的前置条件）

进入 `/rec-dev` 前必须确认：
- `/rec-plan` 已完成且规划已确认
- 涉及 metadata 变更的 item 已标注
- 验收标准已定义且可映射到 T1~T4
- 推荐域归属 `L1/L2/L3` 已明确

任一未满足：`GATE_BLOCK`

## 执行姿态（与 /dev 完全对齐）

AI Agent 执行 `/rec-dev` 时，**必须先进入任务级 plan mode**：

1. 通读 `/rec-plan` 中目标 item 的验收标准、影响面、DDD 约束、端云对齐要求
2. 审视 metadata/codegen、前后端影响面、测试层覆盖
3. 若发现缺口（验收不完整、端云不对齐、测试策略缺失），先自动修复再继续
4. 派生覆盖全部未完成 item 的会话 todo

**禁止**：
- 仅完成后端不做前端、或仅做前端不改 metadata
- 跳过 codegen 直接手写 DTO / struct
- 用 `interface{}` / `Map<String, dynamic>` 传递推荐特征
- 在 `runtime/recommendation/` 中 import `go.mongodb.org` 或 `go-redis`
- 不写测试就宣布完成
- 明知端云字段不对齐仍继续

## 实施顺序（强制，与 SDD metadata-first 对齐）

```
1. metadata YAML    — feature_registry.yaml / service.yaml / errors.yaml / redis_keyspace.yaml
2. make verify      — make -C quwoquan_service verify-metadata
3. make codegen     — make codegen && make codegen-app
4. domain/runtime   — runtime/recommendation/ 下的纯逻辑（无 DB import）
5. infrastructure   — services/content-service/internal/infrastructure/recommendation/
6. application      — services/content-service/internal/application/ 组装
7. adapters/http    — services/content-service/internal/adapters/http/ 暴露
8. dart cloud       — lib/cloud/services/behavior/ + lib/core/trackers/
9. dart ui          — lib/ui/**/pages/ 接入
10. test            — T1 单元 → T2 契约 → T3 端云 → T4 旅程
```

## DDD 分层检查清单（每个 item 强制）

```
☐ 新增域逻辑在 runtime/recommendation/（无 DB import）
☐ 新增存储在 infrastructure/recommendation/（interface 定义在上层）
☐ 新增 HTTP 在 adapters/http/（调用 application 层）
☐ application 层只做组装编排（不含业务规则）
☐ domain → application → adapters → infrastructure 单向依赖
```

## 强类型检查清单

```
☐ Go: UserFeatureVector 新增字段为具体类型（非 interface{}）
☐ Go: BehaviorSignal 新增字段为具体类型（非 interface{}）
☐ Go: ContentCandidate 新增字段为具体类型
☐ Dart: BehaviorEvent 新增字段为具体 Dart 类型
☐ Dart: UI/Provider 不直接操作 Map<String, dynamic>
☐ Dart: 推荐相关 DTO 使用 PostBaseDto 子类或强类型 ViewModel
☐ 枚举值端云统一（Dart enum string ↔ Go const string）
```

## 端云一致检查清单

```
☐ Dart BehaviorEvent 字段集 ⊇ Go BehaviorSignal 字段集
☐ Dart toJson() key == Go JSON tag
☐ Dart ReferralSource 枚举值 == Go ReferralSourceMultiplier key
☐ feature_registry.yaml features ⊆ Go UserFeatureVector fields
☐ feature_registry.yaml labels ⊆ Go BehaviorSignal 可推导字段
☐ verify_feature_consistency.py 通过
```

## 存储无关检查清单

```
☐ FeatureStore 是 interface（非 struct）
☐ BehaviorEventStore 是 interface
☐ BulkImportStore 是 interface
☐ DiscoveryFeedProjector 不直接 import mongo driver
☐ RecommendFeatureProjector 不直接 import mongo driver
☐ 切换存储只需替换 infrastructure 实现 + main.go 注入
```

## 四层测试检查清单

```
☐ T1: 每个新增 public func 在 *_test.go 有单元测试
☐ T1: 每个新增 Dart 方法在 *_test.dart 有单元测试
☐ T2: verify_feature_consistency.py 端云 schema 对齐
☐ T2: behavior_repository_contract_test.dart 契约覆盖新字段
☐ T2: make test-contract 通过
☐ T3: 端云联调（若涉及新 API endpoint）
☐ T4: Patrol 推荐 feed 旅程（若涉及 UI 变更）
```

## 可观测交叉 Checklist（推荐 × 可观测联动）

```
☐ 新增推荐行为信号 → 已同步到 obs-audit D1 的采集范围
☐ 推荐管线各阶段延迟 → 已暴露为 Prometheus metric
☐ 新增 AB 实验桶 → 指标大盘可按桶切分
☐ 新增特征 → feature_registry 版本 +1 → 训练管线同步
☐ 新增 API endpoint → 已有 HTTP 延迟 histogram
```

## 验证门禁（必须全部通过才可收口）

```bash
# Go 编译
cd quwoquan_service && go build ./...

# 推荐引擎单元测试（T1）
cd quwoquan_service && go test ./runtime/recommendation/... -v -count=1

# 内容服务集成测试（T2）
cd quwoquan_service && go test ./services/content-service/... -v -count=1

# 特征一致性校验（T2）
cd quwoquan_service && python3 scripts/ml/verify_feature_consistency.py

# 端侧分析
cd quwoquan_app && dart analyze lib/cloud/services/behavior/ lib/core/trackers/

# 端侧契约测试（T2）
cd quwoquan_app && flutter test test/cloud/behavior/

# DDD 导入约束扫描
cd quwoquan_service && python3 -c "
import pathlib
violations = []
for f in pathlib.Path('runtime/recommendation').rglob('*.go'):
    content = f.read_text()
    for banned in ['go.mongodb.org', 'github.com/go-redis', 'database/sql']:
        if banned in content:
            violations.append(f'DDD_VIOLATION: {f} imports {banned}')
if violations:
    for v in violations: print(f'✗ {v}')
    exit(1)
else:
    print('✓ DDD recommendation layer: PASS')
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
推荐实施、验证与归档完成：recommendation-<scope>
items 完成：N/N
DDD 合规: PASS
端云一致: PASS
T1~T4: T1 ✓ T2 ✓ T3 ○ T4 ○
verify: PASS
archive: DONE
下一步：/commit
```

## 与其他命令的关系

| 命令 | 角色 | 等价于 |
|------|------|--------|
| `/rec-audit` | 自检评审 | `/explore` 的推荐专项 |
| `/rec-plan` | 能力规划 | `/baseline` 或 `/prd`+`/design` |
| `/rec-dev` | 实施开发 | **`/dev`**（完整闭环） |
| `/rec-bench` | 效果评估 | 对标分析 |
| `/commit` | 提交 | 提交（与主流程共用） |
