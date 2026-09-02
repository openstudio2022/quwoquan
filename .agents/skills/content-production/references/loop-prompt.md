# Loop prompt（冻结，宿主无关）

`loop_driver.sh` 每轮把下方正文原样交给宿主命令（`$HOST_CMD`），并替换
`<executionId>` 占位符。修改正文语义视为契约变更，必须过评审；驱动脚本
不得内联复制本段（第二真相源禁令）。

---

读 `.agents/skills/content-production/SKILL.md`。对 `<executionId>` 按
`references/recovery.md` 判定表定位断点。只执行**一个**阶段的做前（PRE）/
做中（DURING）/做后（POST）。通过后依次调用 `task stage-gate` 与 `task stage-close`，由 authority 派生 receipt 后退出 0。
blocked 时落 `verdict=blocked` receipt 后退出 2。不要开始下一个阶段。
