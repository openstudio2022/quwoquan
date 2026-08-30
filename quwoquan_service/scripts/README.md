# quwoquan_service/scripts

Service 侧 Python/Shell 脚本按真实 owner 归档，不维护第二套 inventory。

## 允许的顶层

| 顶层 | 用途 |
|---|---|
| `contracts/` | build / sync / generate（可写回 metadata 的 mutating 工具） |
| `codegen/` | 生成运行时/编译产物（须同时提供 generate 与 `--check`） |
| `runtime/<concern>/` | 运行时横切；concern 闭集：`packaging` / `experiments` / `reliabletask`；禁止平铺在 `runtime/` 根 |
| `verify/<theme>/` | **仅**跨服务 / 契约结构 gate；主题口袋如 `contract_graph` / `structure` / `consistency` / `observability`；禁止写回 metadata；禁止 `verify/<kebab-service>/` |
| `tools/` | 真正跨服务的人工工具（如 `observability/`）；禁止单服务岛 |
| `<kebab-service>/` | L1=服务名镜像；服务级脚本可停在 L1；对象专属必须落到真实 `internal/<context>/<object>`；人工工具进服务内 `tools/` |

禁止：`scripts/service/` 包装层；`contract/`（单数）、`recommendation/`（非 kebab）、`persona/` 业务脚本岛；禁止在顶层 `tools/` 下再放 `search/`、`product_ops/` 等单服务目录；禁止旧路径 shim。

`environments/{alpha,beta,gamma,prod}`、`deploy/`、`config/` **只**存在于 `services/<kebab-service>/`；scripts 树不复制服务包布局。

治理：`verify_python_script_governance --scope service` 对 `runtime/` 平铺发出 `SERVICE.RUNTIME_FLAT_SCRIPT`；对「`verify/**` 内扫描根仅命中单服务」发出 `SERVICE.VERIFY_SINGLE_SERVICE_OWNER` warn。
所有 verifier 必须证明目标根存在并至少命中一份真实源码；空扫描不得报告通过。
`services/**` 内的 Python production module、generated 与三层测试虽然不承担 scripts
角色，也必须分别由 service layering、codegen 与 test-directory-layout 门归类，禁止
成为脚本治理枚举之外的未知 Python 文件。

## 角色

稳定角色闭集：`gate / cli / lib / generator / runner / tool / migration / hook`。  
命名优先 `verify_`、`generate_`/`gen_`/`sync_`/`build_`、`run_`；服务内 `tools/`
下为 tool。人工 tool 必须由本 README、CLI、Make、runbook、spec 或测试中的至少一处
当前引用证明 owner 与用途。

## 常用入口

```bash
make -C quwoquan_service verify-metadata
make -C quwoquan_service verify-redis-routes
make -C quwoquan_service verify-content-architecture
make -C quwoquan_service gate
python3 -B quwoquan_ops/gate/verify_python_script_governance.py --scope service --mode check
```

Prod 发布的对象模型兼容门禁必须显式绑定 hosted immutable baseline，不能加入只读源码
`gate` 后用本地文件伪造通过：

```bash
make -C quwoquan_service verify-domain-model-compatibility \
  DOMAIN_MODEL_BASELINE_RECEIPT=<hosted-full-or-100-receipt-readback.json> \
  DOMAIN_MODEL_BASELINE_GRAPH=<exact-baseline-contract-graph.json> \
  DOMAIN_MODEL_CURRENT_GRAPH=generated/contract_graph.json \
  DOMAIN_MODEL_COMPATIBILITY_WINDOW=<minimum-build-window.json> \
  DOMAIN_MODEL_STORAGE_MIGRATION_PLAN=<quiesced-migration.json>
```

该工具只写 `.qwq_output/env/repo/runs/domain-model-compatibility/report.json`，阻断
错误 `major.minor`、未关闭的 App minimum window、非静默原子 storage migration
以及任何 dual-read/dual-write；它不改写 metadata。

## 领域服务脚本示例

- `search-service/tools/search_load_benchmark.py`
- `content-service/content/content_behavior_fact/verify_daily_metrics_dimension_consistency.py`
- `entity-service/entity_homepage/homepage/verify_entity_homepage_object_mainline.py`
- `assistant-service/assistant/assistant_run/verify_assistant_context_contract.py`
- `product-ops-service/tools/rec_policy_advisor.py` — 建议-only，不自动激活策略
- `product-ops-service/tools/eval_content_flywheel_loop.py` — 飞轮闭环实证
- 对应 local_contract：`quwoquan_ops/tests/local_contract/test_*__product_ops_tool__local_contract_test.py`

源码树禁止 Python/lint/test 缓存、编辑器备份和临时脚本；可再生产输出只进入
`.qwq_output/**` 或受管仓外缓存。
