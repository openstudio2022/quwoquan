# Flutter 调试与代理绕过

## 现象与边界

系统或工具代理（例如 Clash、Charles、公司代理）若接管 loopback WebSocket，`flutter run` 连接 Dart VM Service 时可能失败：

```text
Error connecting to the service protocol: failed to connect to
http://127.0.0.1:<dynamic-port>/... HttpException: Connection closed before full header was received
```

字面 `flutter run` 经受管 dispatcher 进入 canonical launcher，与 `run.sh` 同样使用动态 loopback 端口（launcher 显式 `--host-vmservice-port=0`、`--dds-port=0`），不保证固定端口。因此代理绕过必须覆盖 `127.0.0.1` / `localhost`，不能只放行某两个端口。本页只说明配置与诊断，不声明当前机器、代理、设备或启动面已经 PASS。

完整入口与证据边界见 [APP_STARTUP.md](APP_STARTUP.md)。

## 先确认终端 PATH 注入

唯一激活入口在仓库根执行：

```bash
make app-activate-flutter-facade FACADE_ACTION="--scope all"
```

激活只前置 launcher bin（含全局 `run.sh` wrapper 与字面 `flutter` dispatcher）与钉定 SDK/CocoaPods/Python 的 PATH 并导出身份变量。Cursor env 变化后执行 **Reload Window** 并新开 terminal。新开的 Terminal/iTerm zsh 自动读取 `~/.zshrc` managed block；已经打开的 zsh 必须显式刷新：

```bash
source ~/.config/quwoquan/flutter-facade.zsh && rehash
```

查看状态或回退：

```bash
make app-activate-flutter-facade FACADE_ACTION="--scope all --status"
make app-activate-flutter-facade FACADE_ACTION="--scope all --deactivate"
```

需要只操作一个 scope 时显式传 `--scope cursor` 或 `--scope user-zsh`。Cursor 回退后 Reload Window；user-zsh 回退后新开 shell。

在已刷新终端中检查并启动（任意工作目录）：

```bash
command -v flutter
flutter run
```

`command -v flutter` 应解析到受管 PATH 首位的 launcher `flutter` dispatcher：`flutter run` 进入 canonical launcher，其余子命令（`doctor`、`--version` 等）exact 透传钉定的真实 SDK。不要在文档、issue、聊天或共享日志中粘贴本机绝对 SDK/Pod/Python identity、HOME、完整 PATH 或 secret。

## 多设备与自动化

- 字面 `flutter run`：无 `-d` 时与 `run.sh` 同一 canonical device authority——单设备自动选择、多设备双 TTY 编号选择、非 TTY typed 阻断；热重载/热重启键位（r/R/q）由 canonical launcher 前台会话提供。
- `run.sh`：无 `-d` 且 stdin/stderr 都是 TTY 时显示编号列表供一次选择；任一流非 TTY 时 typed block，CI/automation 必须传 `-d <flutter-device-id>`。显式 ID 按 exact identity 校验，不能依赖“最近使用设备”。
- `flutter run` 与 `run.sh` 都不要手工传 `--host-vmservice-port`、`--dds-port` 或 `--no-pub`：canonical launcher 统一管理端口；dispatcher 对白名单（`-d`、`-v`）以外的 run 参数输出 `APP.LAUNCH.managed_argument_unsupported: <参数>` 并 exit 2。

## 代理绕过配置

### 环境变量

在代理实际读取的 shell startup 文件中保留已有值，并追加 loopback 主机：

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"
```

修改后新开 shell，或在当前 zsh 中先显式 source 上述 managed config 并 `rehash`，确保代理变量与最终 PATH 同时生效。

### Clash / Charles / 公司代理

把以下主机加入 `DIRECT` / Bypass / Exclude：

- `127.0.0.1`
- `localhost`

若工具只能按网段配置，使用其官方 loopback 绕过方式。不要仅放行固定端口，因为 VM Service 与 DDS 端口动态分配。

### Cursor / VS Code 代理

在编辑器代理设置中把 `127.0.0.1,localhost` 加入 Proxy Bypass / No Proxy。不要手改用户全局 Cursor terminal profile；工作区受管块只由具名激活入口管理。

## 验证与诊断

1. 在目标 shell 确认 `command -v flutter` 与 `command -v run.sh` 都解析到仓库 launcher bin。
2. 开启代理后执行 `flutter run`（任意工作目录），观察 attach 与 Hot Reload/Restart。
3. 多设备交互仅用于双 TTY；无交互执行必须显式 `-d`。
4. 若 loopback 握手仍失败，确认代理是否真正绕过动态 `127.0.0.1:<port>`，再使用 `agents-window` 做可选诊断；optional diagnostics 不是 required surface receipt。
5. 成功一次只证明该次设备、shell 与代理配置，不等于其他 surface、环境 lifecycle、runtime health 或 UAT 已通过。

一切 buildMode/buildProfile 缺 canonical trust 时必须 fail closed（构建期默认供给已退役，无物化例外）；用真实 SDK 绝对路径绕过 dispatcher 的 raw `flutter run` 会在 trust gate 以 `APP.LAUNCH.runtime_config_trust_missing` 阻断。恢复动作只能回到具名激活/刷新入口、字面 `flutter run`、`run.sh` 或受控制 IDE profile，不得关闭 Prod trust gate。
