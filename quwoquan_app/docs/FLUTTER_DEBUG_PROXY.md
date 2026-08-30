# Flutter 调试与代理绕过

## 现象与边界

系统或工具代理（例如 Clash、Charles、公司代理）如果接管 loopback WebSocket，`flutter run` 连接 Dart VM Service 时可能失败：

```text
Error connecting to the service protocol: failed to connect to
http://127.0.0.1:<dynamic-port>/... HttpException: Connection closed before full header was received
```

当前 canonical launcher 使用动态 loopback 端口（`--host-vmservice-port=0`、`--dds-port=0`），不保证 `8888/8889`。因此代理绕过必须覆盖 `127.0.0.1` / `localhost`，不能依赖固定端口。本页只给出配置与诊断方法，不声明当前机器、当前代理或任一启动面已经 PASS。

完整的四个公开入口见 [APP_STARTUP.md](APP_STARTUP.md)。

## 先恢复 canonical 启动面

Workspace Terminal 与 IDE 首次使用时，在仓库根运行：

```bash
make app-activate-flutter-facade
```

然后执行 **Reload Window**，关闭旧终端并打开一个全新的 Workspace Terminal。旧 PTY 的 PATH 与 terminal receipt 不会被就地升级；准确恢复动作是“重新激活 → Reload Window → 新建 Workspace Terminal”，不是修改全局 PATH、关闭 trust gate 或直接调用绝对路径 Flutter SDK。

在 fresh Workspace Terminal 中检查并启动：

```bash
command -v flutter
flutter run -d <flutter-device-id>
```

`command -v flutter` 必须解析到 `quwoquan_app/scripts/tools/flutter_facade/bin/flutter`。不要手工传 `--host-vmservice-port`、`--dds-port` 或 `--no-pub`。IDE 使用 `QuWoQuan: canonical launch + IDE attach` profile；`agents-window` 仅为 optional diagnostics，不是字面 `flutter run` 或 UAT 的 required surface。

查看投影状态：

```bash
make app-activate-flutter-facade FACADE_ACTION=--status
```

## 代理绕过配置

### 环境变量

在代理实际读取的 shell startup 文件中保留已有值，并追加 loopback 主机：

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"
```

修改后仍须 Reload Window 并新建 Workspace Terminal，让代理变量和 facade 的最终 PATH 在同一个 fresh PTY 中生效。

### Clash / Charles / 公司代理

把以下主机加入 `DIRECT` / Bypass / Exclude 列表：

- `127.0.0.1`
- `localhost`

若工具只能按网段配置，可使用其官方方式绕过 loopback。不要仅放行 `8888/8889`，因为当前端口是动态分配的。

### Cursor / VS Code 代理

在编辑器代理设置中，把 `127.0.0.1,localhost` 加入 Proxy Bypass / No Proxy。不要为了获得启动通过而修改用户全局 Cursor terminal profile；工作区入口投影只由 `make app-activate-flutter-facade` 管理。

## 验证与诊断

1. 在 fresh Workspace Terminal 确认 `command -v flutter` 指向仓库 facade。
2. 开启代理后执行受支持入口并观察是否成功 attach、Hot Reload/Restart。
3. 若仍出现 loopback 握手错误，先确认代理工具是否真正绕过动态 `127.0.0.1:<port>`，再用 `agents-window` 做可选诊断；不要把可选诊断结果当作 required surface receipt。
4. 成功一次只证明该次设备、PTY 与代理配置；不等于其他启动面、服务 lifecycle、App receipt 或 UAT 已经通过。

`quwoquan_app/run.sh` 是 internal executor / 高级诊断入口，不是新增的公开角色入口。直接使用它也不能绕过 canonical trust、设备 binding、启动 receipt 或 stackctl 管理的服务 lifecycle。
