# ops · dev · gate

适用：改动新增或修改 gate 脚本、`Makefile` gate 目标或 CI workflow 接线。

## DURING 执行中

- [MUST] 新增 gate 声明触发范围（哪些路径/交付件）、阻断条件与修复方式
  check: gate 脚本头部或对应文档缺任一项，判失败
- [MUST NOT] gate 失败被包装为警告或成功退出码
  check: 脚本在检测到违规后 `exit 0` 或仅打印 warning，判失败

## POST 自检

- [MUST] 新增 gate 已接入 `make gate` / `gate_repo.sh`
  check: 新增 gate 脚本但未在 `Makefile` 与 `gate_repo.sh` 中出现，判失败
- [MUST] gate 有配套的正/反 fixture 场景，证明它抓得住违规、放得过合规
  check: 无任何失败场景证据，判失败

## HANDOFF 交接

- 产出：gate 接线点与 fixture 证据
- 未决项去向：未接线或未验证的 gate 转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：gate 在正反场景下的实际输出
