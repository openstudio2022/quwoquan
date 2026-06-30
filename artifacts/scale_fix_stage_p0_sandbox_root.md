# P0 输出根归位 + 运行时隔离（阶段证据）

## 目标
默认运行时根从用户 HOME 的 `~/qwq_scale_verify` 归位到 quwoquan 项目内 gitignored sandbox
`.qwq_sandbox/`，并保证 gate 的 `verify --scope current` 不被 sandbox release 污染。

## 改动
- `quwoquan_data/scripts/_common/paths.py`：新增 `DEFAULT_SANDBOX_ROOT = REPO_ROOT/.qwq_sandbox`
  与 `default_sandbox_root()`（沙箱默认根的单一真相源）。**不改 DATA_ROOT 默认**——gate/测试仍用
  仓库 `quwoquan_data` 数据根，sandbox 是 opt-in（经 `QWQ_DATA_ROOT` 指向 `.qwq_sandbox`）。
- `.gitignore`：新增 `.qwq_sandbox/`（整 sandbox 不进 git）。
- `agent_ops/runners/*.sh`（14 个）：`QWQ_DATA_ROOT` 默认值
  `$HOME/qwq_scale_verify` → 自包含的仓库相对 `$(... )/.qwq_sandbox`，移除 HOME 漂移。
- `quwoquan_data/tests/local_contract/common/test_sandbox_root_isolation__local_contract_test.py`：
  新增隔离契约（sandbox 在仓库内/非 HOME scratch、无 runner 仍默认 qwq_scale_verify、
  指向 sandbox 时 runtime/publish/release 跟随而 schema/contracts 跟代码走、
  sandbox release 与 gate 默认 release 根物理隔离）。
- `verify_quwoquan_data.sh`：接入上述隔离测试。

## 隔离不变量（根变量分层）
| 数据 | 默认根 | 是否随 sandbox 漂移 |
|---|---|---|
| runtime/publish/release | `DATA_ROOT/{runtime,publish,release}` | 是（指向 sandbox 即落 sandbox） |
| schema | `_REPO_DATA_ROOT/schema` | 否（跟代码） |
| 服务侧 contracts/metadata | `REPO_ROOT/quwoquan_service/contracts/metadata` | 否（跟代码） |
| gate 默认 release（verify --scope current 扫描面） | `quwoquan_data/release` | 否，与 sandbox release 物理隔离 |

## 证据
- `pytest test_sandbox_root_isolation__local_contract_test.py` → 3 passed。
- `bash -n agent_ops/runners/*.sh` → all parse OK。
- 默认 token 解析：`/Users/.../quwoquan/.qwq_sandbox`（仓库内）。
