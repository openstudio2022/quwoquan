# Data Portal

本目录是 loopback-only 的 React/Vite 前端，只消费 `operations.json` 声明的 canonical `/api/*`。浏览器详情路由保持 `/works/:objectKey`，其中 `objectKey` 为 `objectId@versionId`，client 解码后请求 `/api/items/{objectId}/{versionId}`。

页面实际复用 `quwoquan_ops/portal/src/shared/ui` 的 `PortalFrame`、`PageScaffold`、`SectionCard` 与 `KpiCard`，并导入 Ops 公共样式；Data 业务组件和样式留在本目录，Ops 不反向依赖 Data。

## 一键启动

在仓库根目录运行：

```bash
make content-workbench
```

该命令依次执行 lockfile 固定的 `npm ci`、Data Portal build 和 Python CLI serve，并自动绑定以下默认值：

- canonical publish root：源码仓平级的 `../publish`（只读）；
- 人工复核台账：`~/.local/share/quwoquan/content-workbench`；
- R1/R2 候选暂存：`~/.local/share/quwoquan/content-workbench-staging`；
- 服务地址：loopback `127.0.0.1:4319`。

无需预先导出环境变量或填写 CLI 参数。命令对冷依赖安装、前端构建和 backend 启动预热分别输出实际耗时；任一阶段失败即停止，不把后续阶段或 URL 报告为成功。CLI 完成 backend 预热后才输出可访问 URL，Makefile 不提前打印地址。按 `Ctrl-C` 停止服务。

## 性能计时边界

工作台的 warm UI 验收边界是：依赖已安装、静态资源已构建、backend 已完成预热后，在同一只读快照上进行常规列表/详情浏览，端到端交互延迟 `p95 ≤ 3s`。该指标不包含冷 `npm ci`、前端 build、backend 启动预热，也不包含用户触发的显式刷新；四类耗时必须分开记录，不能用 warm UI 指标掩盖冷启动或刷新成本。

显式刷新会重新读取当前 canonical publish root 与本地台账，其耗时单独计量；它不是 warm 页面切换，也不应与安装、构建或启动预热合并。

## 详情证据边界

详情中的 adopted source、授权/许可、归属、生产 review 和绑定摘要，均从 canonical 对象包内的本地冻结证据读取并核对；工作台不联网补全、不把缺失字段推断为已授权或已通过。详情展示的外链源站只是该冻结证据记录的当前网页 URL，点击后看到的源站内容可能已变化，因此外链网页不是本次离线复核的事实 authority，也不能覆盖本地冻结证据。
