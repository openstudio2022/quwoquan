# environment-operator

- **职责**：环境打包、启动、健康检查与巡检；不做发布，不做修复。
- **输入**：目标环境 / target、服务清单、profile。
- **输出**：环境报告与运行证据（`.qwq_output/env/<env>/runs/<run-id>/`）。

## 典型序列

本地 beta 联调：

1. `stackctl package --env beta --include-services`
2. `stackctl up --env beta`
3. `stackctl health --target beta-local --scope full`
4. `stackctl inspect --target beta-local --kind all`

local-gamma mirror：同上，把 `beta` 换成 `gamma`、target 换成 `gamma-local`。

本地 prod / prod-sim 连接：

- `prod-sim` 用 `stackctl up --env prod-sim`。
- `prod` 用 `stackctl up --env prod`，先对 `prod-hosted` 执行 edge health，再拉起本地 App/浏览器。
- 不为 prod attach 另写第二套 gateway/media 参数；public base 统一来自 `prod/runtime.yaml`。
