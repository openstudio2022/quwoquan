# Flutter 调试与代理绕过

## 问题

在开启系统/工具代理（如 Clash、Charles、公司代理）时，`flutter run` 连接 Dart VM 服务（WebSocket）可能被代理拦截，导致：

```
Error connecting to the service protocol: failed to connect to
http://127.0.0.1:xxxxx/... HttpException: Connection closed before full header was received
```

且每次运行端口都会变化，无法在代理里固定放行。

## 解决方案

### 1. 固定 VM 服务端口（已配置）

- **VM Service**：`127.0.0.1:8888`（调试/热重载）
- **DDS**：`127.0.0.1:8889`（Dart Development Service）

本仓库的启动入口还负责 runtime trust、环境 binding、启动回执与设备 lease，不能绕过。
请选择下列 canonical 入口之一：

- **推荐**：在 `quwoquan_app` 目录下用脚本启动（固定端口）：
  ```bash
  cd quwoquan_app
  ./run.sh -d <device-id>
  ```
  设备 ID 可由 `flutter devices` 查询；`run.sh` 要求显式 `-d`。

- **Cursor 工作区字面 `flutter run`**：先在仓库根执行：
  ```bash
  make app-activate-flutter-facade
  ```
  然后执行 **Reload Window**，打开一个全新的工作区终端，确认
  `command -v flutter` 指向 `quwoquan_app/scripts/tools/flutter_facade/bin/flutter`，
  再运行唯一允许的字面命令 `flutter run -d <device-id>`。facade 会转交 canonical
  launcher；不要手工传 `--host-vmservice-port`、`--dds-port` 或 `--no-pub`。

在 **Cursor/VS Code** 里用「运行」或「调试」按钮启动时，同样必须先完成上述
workspace activation 与 Reload Window，IDE profile 才会走受管入口。

可选：在 `~/.zshrc` 加别名，以后在任意目录可打 `fr` 即用固定端口（需先在 quwoquan_app 下执行）：
```bash
alias fr='cd /path/to/quwoquan_app && ./run.sh'
```

### 2. 代理绕过配置（不代理本机调试端口）

让代理**不要**代理对 `127.0.0.1` 的访问，或至少不代理上述端口。

#### 方式 A：环境变量（推荐）

在 `~/.zshrc`（或 `~/.bash_profile`）中增加：

```bash
# Flutter/Dart VM 服务直连，不走代理
export NO_PROXY="127.0.0.1,localhost,127.0.0.1:8888,127.0.0.1:8889"
# 若已有 NO_PROXY，在其后追加：,127.0.0.1,127.0.0.1:8888,127.0.0.1:8889
```

保存后执行 `source ~/.zshrc`。之后在终端里执行 `flutter run` 时，对 127.0.0.1 的请求不会走代理。

#### 方式 B：Clash / 代理工具「绕过」规则

在 Clash（或同类工具）的规则 / 绕过列表中添加：

- 域名：`127.0.0.1`、`localhost`
- 或端口：`8888`、`8889`

具体名称因客户端而异，常见为「绕过列表」「Bypass」「直连」等，把上述主机/端口加入即可。

#### 方式 C：Cursor / VS Code 代理设置

若 Cursor 使用自己的 HTTP 代理设置，且会代理本机请求：

1. 打开设置，搜索 `proxy`
2. 若有「Proxy Bypass」或「No Proxy」列表，加入：`127.0.0.1,localhost` 或 `127.0.0.1:8888,127.0.0.1:8889`

这样 IDE 发往 VM 服务的连接不会经代理。

## 检查是否生效

1. 确认入口和端口：新工作区终端先运行 `command -v flutter`，再运行
   `flutter run -d <device-id>`；启动日志应出现受管入口及 `127.0.0.1:8888`。
2. 确认绕过：开启代理的情况下，能正常连接并热重载、无 “Connection closed before full header” 即表示绕过生效。
