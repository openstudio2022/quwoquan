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

**在终端里**直接执行 `flutter run` 不会使用固定端口（端口由 Flutter 随机分配），所以必须二选一：

- **推荐**：在 `quwoquan_app` 目录下用脚本启动（固定端口）：
  ```bash
  cd quwoquan_app
  ./run.sh
  ```
  如需传参给 `flutter run`，可写在后面，如：`./run.sh -d "iPhone 16 Pro Max"`。

- 或手动带参数：
  ```bash
  flutter run --host-vmservice-port=8888 --dds-port=8889
  ```

在 **Cursor/VS Code** 里用「运行」或「调试」按钮启动时，会读取 `.vscode/settings.json`，自动使用上述固定端口。

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

1. 确认端口固定：运行 `flutter run --host-vmservice-port=8888 --dds-port=8889`，日志里应出现 `127.0.0.1:8888`。
2. 确认绕过：开启代理的情况下，能正常连接并热重载、无 “Connection closed before full header” 即表示绕过生效。
