# L3 细节：environment-topology-and-packaging

## 功能说明

统一定义当前环境集合（如 `alpha / beta / gamma / prod`）的 topology schema、public/upstream/origin 分层、artifact policy、host allowlist、secret scope 与 package purity 门禁。

统一真相源：

- `quwoquan_ops/environments/environment_topology_manifest.yaml`
- `quwoquan_ops/environments/local_env_port_manifest.yaml`

## 核心约束

- 当前环境集合都必须声明完整 `edge / media / service / data` 子网与 public base 字段。
- `alpha` 只能通过 `mockBoundaryFlags` 区分，不得删字段、删平面、删 schema。
- 本地 host 端口必须来自 1000 端口块 + plane + 10 端口槽位模型，canonical 端口以 `0` 结尾。
- App / Service env package 都必须携带 topology schema 版本、artifact policy 摘要与机器可读报告。
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- `prod` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL。

## 门禁与证据

- `verify_environment_topology_manifest.py`
- `verify_local_env_port_manifest.py`
- `verify_public_vs_upstream_url_contract.py`
- `verify_environment_packaging_contract.py`
- `verify_env_artifact_isolation.py`
- `verify_prod_package_purity.py`

## 验收标准

- A1：当前环境集合的 topology schema 完整且一致。
- A3：环境包与产物隔离由门禁自动阻断。
- A7：public base / upstream base / origin base 语义不混用。
- A8：本地、hosted、prod 的 artifact policy 与 host allowlist 可审计。
