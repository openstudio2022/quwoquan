# L3 特性：optimization-evaluation-and-release（策略评估与发布）

## 功能说明

把推荐评分策略从"硬编码常量"迁移为"元数据驱动 + 热加载 + 顾问建议 + 人审发布"：

- `policy.yaml` 定义 12 维权重预设、二级系数、AB 实验（bucket→preset/model）、
  segment 定向（preset 覆盖 / 权重增量）、护栏（KPI 下限，`suggest_only`）。
- `codegen_rec_policy` 生成强类型 baseline（`rec_policy_baseline.gen.go`）作 fail-safe。
- `runtime/recpolicy.Store` 热加载 `policy.yaml`：`atomic.Pointer` 读、validate-before-swap、
  last-good 保留；`StartSyncLoop` 按文件 mtime 周期重载。
- 推荐引擎 `GetFeed` 在拿到用户 segments 后，调用 `ResolveBucketOr` / `ResolveWeights`
  得到 `ResolvedPolicy`，据此取权重、二级系数、模型分桶、重排多样性/冷启阈值。
- `rec_policy_advisor.py` 对照护栏评估 cohort（preset×segment×bucket）KPI，产出
  `recommend_review/hold/reject` 建议；至多把候选推进到 product-ops `:simulate`，
  **绝不** `:activate`。

## 约束

- 评分相关一切数字（权重/系数/实验比例/定向/阈值）唯一来自 `policy.yaml`；引擎与脚本禁止硬编码。
- 护栏 `action` 只允许 `suggest_only`；顾问无 `:activate` 代码路径。
- 热更必须 validate-before-swap；坏 YAML 拒绝并保留 last-good，禁止"坏 YAML 置零打分"。
- baseline 仅在启动前/坏 YAML 时兜底，且来自同一 metadata + `make gate` hash 校验，非手写常量。

## 验收标准

- A1：policy.yaml 改权重/系数/实验/定向即热生效（无需重启/改代码）。
- A2：坏 policy 被 `Validate` 拒绝并保留 last-good；缺实验/缺 baseline 走声明式 fallback。
- A5：顾问只产建议，至多 `:simulate`，无 activate 路径；护栏命中产 `reject/hold`。
- A6：`PipelineMetrics` 与 `rec_requests_by_policy_total` 按 policyVersion×preset×segment 归因。
- A7：`policy.yaml` 通过 `make verify-metadata`；codegen baseline 与 metadata 无 diff。
- A8：对应自动化测试映射完整（见 acceptance.tests.recorded）。
