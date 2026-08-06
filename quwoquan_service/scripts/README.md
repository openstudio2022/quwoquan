# quwoquan_service/scripts

Service 侧 Python/Shell 脚本按真实 owner 归档，不维护第二套 inventory。

## 允许的顶层

| 顶层 | 用途 |
|---|---|
| `contracts/` | build / sync / generate（可写回 metadata 的 mutating 工具） |
| `codegen/` | 生成运行时/编译产物（须同时提供 generate 与 `--check`） |
| `runtime/` | 运行时横切：packaging、experiments、reliabletask 等 |
| `verify/` | 跨服务 / 契约结构 gate；禁止写回 metadata |
| `tools/` | 人工/产品运营工具（如 `product_ops/`、`observability/`） |
| `<kebab-service>/` | 只属于该服务的脚本；可下钻到 `internal` 真实存在的 `<context>/<object>` |

禁止：`contract/`（单数）、`recommendation/`（非 kebab）、`persona/` 业务脚本岛。

## 角色

稳定角色闭集：`gate / cli / lib / generator / runner / tool / migration / hook`。  
命名优先 `verify_`、`generate_`/`gen_`/`sync_`/`build_`、`run_`；`tools/` 下为 tool。

## 常用入口

```bash
make -C quwoquan_service verify-metadata
make -C quwoquan_service verify-redis-routes
make -C quwoquan_service verify-content-architecture
make -C quwoquan_service gate
python3 -B quwoquan_ops/gate/verify_python_script_governance.py --scope service --mode check
```

## 产品运营工具

- `tools/product_ops/rec_policy_advisor.py` — 建议-only，不自动激活策略
- `tools/product_ops/eval_content_flywheel_loop.py` — 飞轮闭环实证
- 对应 local_contract：`quwoquan_ops/tests/local_contract/test_*__product_ops_tool__local_contract_test.py`
