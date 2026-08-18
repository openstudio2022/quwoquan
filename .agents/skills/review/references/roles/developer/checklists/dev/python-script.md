# developer · dev · python-script

适用：改动新增、移动、重命名或删除 `.py` 脚本。
真相源：[python-scripts](../../references/python-scripts.md)。

## DURING 执行中

- [MUST NOT] 稳定脚本使用 `gate / cli / lib / generator / runner / tool / migration / hook`
  之外的角色，或落在角色规定目录之外
  gate: make verify-python-script-governance
- [MUST NOT] 提交脚本 registry、inventory、债务 baseline 或 orphan allowlist
  gate: make verify-python-script-governance
- [MUST NOT] 源码树保留 `__pycache__/`、`*.pyc`、`.pytest_cache/`；缓存重定向到
  `.qwq_output/env/repo/local/**`
  gate: make verify-python-script-governance

## POST 自检

- [MUST] Python 脚本治理通过
  gate: make verify-python-script-governance

## HANDOFF 交接

- 产出：脚本增删改清单与角色归位
- 未决项去向：无法归位的脚本转 `OPEN-###` 或删除
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
