# guide · python-script

按需正文，不进 Reviewer 派发上下文。判据只在 checklist 与命名 evidence，本文件只提供做法、实测违规案例与修复步骤。

owner 决策：[DEC-034 标识符描述角色，可变闭集的基数只存在于唯一声明源](../../../../../specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-034)

## 可变基数标识符

`quwoquan_ops/cli/**`、`quwoquan_ops/gate/**` 与 `quwoquan_ops/ci/**` 大量消费环境、target、平面与阶段这类会增减的闭集，是本坏味道的高发区。

### 怎么做

名字写它做的事，成员从唯一 canonical 源发现。环境与 target 闭集的声明源是 [`environment_topology.py`](../../../../../quwoquan_ops/cli/lib/environment_topology.py) 的 `ENVIRONMENTS` 与 `TARGETS`，物理事实在各 `quwoquan_ops/environments/<env>/runtime.yaml`。

```python
# 名字只说「读取各 runtime target 的 buildImages」，没有承诺个数
def load_target_build_images(source_root: Path | None = None) -> dict[str, dict[str, str]]:
    for env_name in ENVIRONMENTS:                      # 成员来自唯一声明源
        runtime = _load(root / f"quwoquan_ops/environments/{env_name}/runtime.yaml")
        for target_name, target in runtime["targets"].items():
            ...
```

判据是一句可回答的话：该数字变化后操作语义是否仍成立。仍成立即属于可变基数，必须移出标识符。

### 违规案例（本仓实测）

`four_env_build_images` 是漂移已经发生的样本：名字声明四环境，函数体遍历的却是五个 target（`alpha-local`、`beta-local`、`gamma-local`、`prod-sim`、`prod-hosted`），而且那张 target 到 runtime manifest 的映射表与 `ENVIRONMENTS` 重复。名字、实现与真相源三者互不一致，增环境时三处都要改。

```python
# 反例：基数进了函数名，成员表又在函数体里重来一遍
def four_env_build_images(source_root: Path | None = None) -> ...:
    environments = {
        "alpha-local": root / "quwoquan_ops/environments/alpha/runtime.yaml",
        "beta-local":  root / "quwoquan_ops/environments/beta/runtime.yaml",
        "gamma-local": root / "quwoquan_ops/environments/gamma/runtime.yaml",
        "prod-sim":    root / "quwoquan_ops/environments/prod/runtime.yaml",
        "prod-hosted": root / "quwoquan_ops/environments/prod/runtime.yaml",
    }
```

同族残量（按「下次改到该文件时一并收敛」处理，不做全仓改名）：

- 测试名把基数写成身份：`test_four_environments_declare_package_owned_graphql_inputs`、`test_hls_cmaf_rollout_defaults_off_in_all_four_environments`、`test_contract_declares_one_elasticsearch_adapter_for_four_environments`、`test_three_environment_uat_separates_offline_from_remote_release_train`、`test_environment_packaging_covers_all_three_envs_by_default`
- 报错串把基数当判据描述：`release_evidence_reader.py` 的 `requiredEvidence.environmentArtifacts is not four-environment`，实际判据是与 `set(ENVIRONMENTS)` 的集合比较，消息应列出期望与实际成员
- 模块说明：`collect_mainline_image_descriptors.py` 的 `Resolve four-environment GHCR tags`
- 门禁文案：`verify_runtime_log_governance.py` 的 `Elasticsearch environment_backends must cover four environments`

不判失败的对照：`ENVIRONMENTS`、`TARGETS`、`LOCAL_TARGETS`、`_FORMAL_LOCAL_TARGETS`、`TEST_DATA_TARGETS`、`WORKLOAD_PLANES`、`REQUIRED_SUBNETS` 都用角色命名，个数留在数据里。

### 不属于本坏味道

这些含数字的标识符是身份而不是当前计数，改名等于改契约：

- 冻结协议 id：`qwq.three-layer-case-results`
- 已发布节点目录名：`four-environment-commercial-login-maturity`、`three-layer-evidence`
- 契约字面量与分桶枚举成员：`two_to_five`、`six_to_fifty`、`dual_approval_pending`
- 镜像 tag 与版本：`golang:1.24-bookworm`、`alpine:3.21`

三层测试金字塔（`local_contract` / `api_integration` / `user_acceptance`）是冻结的证据协议，环境集合是可增减的部署闭集，两者不同类，不要一起处理。

### 修复步骤

1. 先问那句判据，确认该数字确实会变
2. 名字改成描述角色或能力，不含基数
3. 删掉函数体内的平行成员表，改为按 canonical 源发现——只改名不改发现，第二真相源仍在
4. 测试名同步去掉基数，断言改为按角色分组（例如 local target 与 hosted target 各自的 pin），不写死成员个数
