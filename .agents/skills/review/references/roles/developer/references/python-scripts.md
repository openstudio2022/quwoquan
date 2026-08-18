# Python 脚本治理

## 角色闭集

稳定脚本角色只允许：`gate / cli / lib / generator / runner / tool / migration / hook`。

角色、owner、引用和 orphan 候选从**当前物理树、Make/workflow/gate/CLI 与 import 关系实时派生**。
禁止提交脚本 registry、inventory、债务 baseline 或 orphan allowlist——这些会立刻变成第二真相源。

## 按树归位

| 树 | 领域 L1 命名 | 下钻与 concern 规则 |
|---|---|---|
| `quwoquan_app/scripts` | 与 `quwoquan_app/lib/service/<service_name>_service` 相同的**下划线**名 | 只在 scope 唯一属于某 context/object 且生产 owner 真实存在时下钻 L2/L3；runtime/platform/tool 按 concern 归档，不得平铺 |
| `quwoquan_service/scripts` | 与 `quwoquan_service/services/<kebab-service>` **同名** | 跨服务能力只进入 `contracts / codegen / runtime / verify / tools` concern；`contracts` 不放 verifier |
| `quwoquan_ops` | concern-first，不按业务特性建脚本岛 | 跨环境验收脚本只进入 `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/<service>`；`producer: ops` 的 readiness case runner 直接指向该树内实现脚本并携带 `readiness_case` / `spec_ref` 双向标注（canonical 形态由 readiness loader 校验） |
| `quwoquan_data/scripts` | CLI-first | 服从 `quwoquan_data/scripts/verify/verify_script_architecture.py`；顶层只允许 `cli.py`、`core/`、`content/`、`governance/`、`verify/` |

## 命名

稳定可执行路径、schema key 和测试标识**禁止**阶段名：`t1..t4`、`m6`、`m7`、`b10`、
`phase0`、`partN` 等。

rename 必须**原子**更新 producer、consumer、import、Make、workflow、测试与文档。
禁止留旧路径 shim。

## orphan 裁决

orphan 只报告，不自动删除。人工裁决只有三种合法结果：

1. 接入 canonical 角色（补 Make/workflow/gate/CLI 引用）
2. 移入 `tools`
3. 连同全部引用一起删除

治理报告写入 `.qwq_output`，对同一物理树必须可重复生成且**字节幂等**。

## 门禁

```bash
make verify-python-script-governance
```
