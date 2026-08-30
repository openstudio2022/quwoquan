# App 启动入口

公开启动面只有四个。它们最终都进入 canonical launcher；不要把 `run.sh`、原始 Xcode/Gradle、绝对路径 Flutter SDK 或设备发现命令包装成新的公开入口。

## 1. 人类一键开发：`make app-dev`

在仓库根运行：

```bash
make app-dev
```

默认值是 `ENV=alpha`、`MODE=content-live`。可显式选择 Alpha/Beta/Gamma、运行模式与设备：

```bash
make app-dev ENV=beta MODE=content-live
make app-dev ENV=gamma MODE=ui-only DEVICE_ID=<flutter-device-id>
```

`ENV` 只接受 `alpha|beta|gamma`，`MODE` 只接受 `content-live|ui-only`（A/B/G only）。省略 `DEVICE_ID` 时由 stackctl 的 canonical device authority 选择唯一设备；有多个候选设备时按其 typed blocker 补传 `DEVICE_ID`。Make 只映射参数，不运行 `flutter devices`，也不解析 target、不持有交互、状态机或 receipt。

`content-live` 要求当前非生产内容 release 与服务 readback；`ui-only` 是显式、不可提升的降级开发模式，不把服务或内容未就绪包装为已通过。

## 2. fresh Workspace Terminal：字面 `flutter run`

首次使用或本地投影失效时，在仓库根执行：

```bash
make app-activate-flutter-facade
```

随后执行 Cursor 的 **Reload Window**，再打开一个全新的 Workspace Terminal。旧 PTY 不会获得新投影，也不能复用其 terminal receipt。新终端中确认：

```bash
command -v flutter
flutter run -d <flutter-device-id>
```

`command -v flutter` 必须解析到仓库内 `quwoquan_app/scripts/tools/flutter_facade/bin/flutter`。不要手工传 `--host-vmservice-port`、`--dds-port` 或 `--no-pub`；facade 会把字面命令归一化到 canonical launcher。`agents-window` 仅可用于 optional diagnostics，不是字面 `flutter run` 或 UAT 的 required surface。

查看投影状态可运行：

```bash
make app-activate-flutter-facade FACADE_ACTION=--status
```

旧 PTY 的准确恢复方式始终是重新运行激活入口、**Reload Window**、关闭旧终端并新建 Workspace Terminal，而不是修改全局 PATH 或 Flutter 安装。需要回退本地投影时运行 `make app-activate-flutter-facade FACADE_ACTION=--deactivate`，然后再次 Reload Window。

## 3. IDE canonical profile

先完成同一激活与 Reload Window，然后在 Cursor/VS Code 的 Run and Debug 中选择：

```text
QuWoQuan: canonical launch + IDE attach
```

该 profile 通过受版本控制源重建的本地 `.vscode/tasks.json` / `.vscode/launch.json` 投影启动 canonical launcher，再由 IDE attach；不要新建第二套 Dart launch profile。环境只选 Alpha/Beta/Gamma，设备 ID 显式输入，模式只选 `content-live|ui-only`。

## 4. AI/自动化 UAT：`make app-uat`

该入口无交互，三个参数都必须显式提供：

```bash
make app-uat \
  TARGETS=alpha-local,beta-local,gamma-local \
  PLATFORM=ios-simulator \
  DEVICE_ID=<flutter-device-id>
```

`TARGETS` 是 `alpha-local|beta-local|gamma-local` 的非空、无重复子集；禁止 Prod。`PLATFORM` 使用 stackctl 当前闭集：`ios-simulator|android|android-physical|ios-physical`。该 adapter 把全局 `--output-format json` 放在 `app-content-uat` 子命令之前，向 AI/自动化返回结构化结果；Make 不扩展 targets，也不代替 stackctl 的 argparse/domain 校验与 UAT raw evidence 编排。

## 生命周期与证据分层

服务 lifecycle 与 App receipt 是两层证据：

- stackctl 管理环境服务的 package/up/health、内容 release/readback 与 teardown；服务就绪不等于 App 已启动。
- canonical launcher 管理 App 的 compile/install/configure/launch、安全终态与启动 receipt；App receipt 不签发服务 lifecycle、内容 readiness、Prod 准出或 UAT authority。
- `app-content-uat` 产生的 raw `ReadinessCaseResult`/父级只读投影也不替代 `run.sh`、fresh Workspace Terminal 或 IDE 三个人类启动面的真实验收。

`quwoquan_app/run.sh` 是 canonical launcher 的 internal executor 与高级诊断入口，不是第五个公开角色入口。只有在定位 launcher/backend 问题或执行既定的人类 surface 证据时才直接调用，并继续要求显式设备与 canonical trust/binding。
