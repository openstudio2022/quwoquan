# App 启动入口

公开启动面只有四个：字面 `flutter run`（受管一键入口，等价进入 canonical launcher）、`run.sh`（canonical launcher）、`make app-dev`/`make app-uat`（编排入口）、IDE canonical profile。终端 PATH 注入是它们的环境前提，不是第五个启动面；不要把原始 Xcode/Gradle、绝对路径 Flutter SDK 或设备发现命令包装成新入口。

## 1. 终端 PATH 注入（一次性激活）

仓库只有一个具名激活入口。在仓库根运行：

```bash
make app-activate-flutter-facade FACADE_ACTION="--scope all"
```

激活只做两件事：把 launcher bin 目录（含全局 `run.sh` wrapper 与字面 `flutter` dispatcher）与钉定的 Flutter/CocoaPods/Python bin 前置到 PATH，并导出对应身份变量。不再有 ZDOTDIR bridge 或 terminal carrier receipt。

- `--scope cursor`（默认）：写入 Cursor `terminal.integrated.env.osx` 受管块与 IDE 投影；完成后执行 **Reload Window**，新开的 Cursor terminal 才消费新 env。
- `--scope user-zsh`：为独立 Terminal/iTerm 的交互 zsh 写入可识别、可移除的 `~/.zshrc` managed block，并生成 `~/.config/quwoquan/flutter-facade.zsh`。显式 opt-in，不会由 build phase 或 App 启动静默修改用户 shell。

新开的终端自动生效；已经打开的 zsh 须显式刷新一次：

```bash
source ~/.config/quwoquan/flutter-facade.zsh && rehash
```

### status 与回退

```bash
make app-activate-flutter-facade FACADE_ACTION="--scope all --status"
make app-activate-flutter-facade FACADE_ACTION="--scope all --deactivate"
```

deactivate 移除全部受管块并逐字保留用户自有内容；Cursor 回退后执行 Reload Window。若受管投影发生 drift，写入路径 fail closed，不会删除无法证明归属的内容。

命令输出只用于状态判断。文档、issue、日志和聊天中不得粘贴本机绝对 SDK/Pod/Python identity、HOME 路径、完整 PATH 或任何 secret。

## 2. 字面 `flutter run`：受管一键入口

在已注入 PATH 的终端、准备启动的 App 工作树（`quwoquan_app/` 或其子目录）：

```bash
flutter run                # 无 -d 时委托 canonical device authority：
                           # 单设备自动、多设备 TTY 编号选择、非 TTY typed 阻断
flutter run -d <device-id> # 显式设备，exact 翻译为 canonical --device
```

- dispatcher 从 cwd 向上定位最近的 `quwoquan_app`，并前台 exec **该工作树**的 `run.sh`；多个 clone/worktree 并存时不会跳回激活 facade 的那棵树。cwd 位于别的 Flutter project 时，`flutter run` 逐字透传真实 SDK；cwd 不属于任何 Flutter project 时才回退 facade 自身所在树。
- App 内的 `run` 白名单翻译为 `run.sh --env alpha --device <id>`，并注入 managed intent：stackctl 控制面先准备并持有 full runtime、consumer lease、所需 transport/receipt、device trust 与严格 preflight，再由同一 `run.sh` 验证和透传这些事实完成 build/install/activation/attach；键位（r/R/q）与字面 direct `run.sh` 相同，但 evidence authority 不同。
- 白名单只有 `-d <id>`/`--device-id <id>` 与 `-v`/`--verbose`（后者以 `QWQ_LAUNCH_VERBOSE=1` 传递）。任何其他参数（`--target`、`--flavor`、`--dart-define*`、`--profile`/`--release`、端口类参数等）输出一行 `APP.LAUNCH.managed_argument_unsupported: <参数>` 并 exit 2；需要这些能力时使用 `run.sh` 的 canonical 参数面。
- 其余全部 flutter 子命令（`--version`、`doctor`、`analyze`、`test`、`pub`、`build` 等）由 dispatcher 解析真实 SDK 后 exact argv/env/cwd 透传，退出码保留；真实 SDK 解析失败输出 typed `APP.LAUNCH.workspace_flutter_sdk_unavailable:` 并退出非零。
- `native_flutter_run` provenance 与 `embedded_default_package` 构建期默认供给已退役：Debug-nonprod 在无 canonical handoff 时不再物化嵌入默认 alpha trust/package。用真实 SDK 绝对路径绕过 dispatcher 的 raw `flutter run` 会在既有 trust gate 以 `APP.LAUNCH.runtime_config_trust_missing` fail-closed。
- 需要非 alpha 环境时使用 `run.sh --env beta|gamma`（见下节）。

## 3. `run.sh`：开发直连与 hermetic 路径

PATH wrapper 与 dispatcher 一样按 cwd 定位工作树；请在准备启动的仓库根、`quwoquan_app/` 或其子目录执行：

```bash
run.sh                                      # Debug-nonprod 开发直连，默认 alpha
run.sh --env beta -d <device-id> --mode ui-only
run.sh --hermetic --env alpha -d <device-id> # 发布级 hermetic 流水线
```

默认开发直连只做：设备/真实 SDK 解析；pub 输入摘要变化时执行可见的 `flutter pub get`；生成签名 handoff/trust；调用既有 executor 完成 build → install → native activation → launch → `flutter attach`。它直接构建当前工作树，不冻结源码、不切 HOME/PUB_CACHE/CocoaPods HOME、不 acquire/bind/release consumer lease、不执行 `adb reverse`、不生成 managed transport receipt 或 launch receipt/test_live report；未知、不可见、非移动或不支持设备在 executor 前 fail closed。若 stackctl 外层已提供经验证的 receipt/lease/handoff 与 cleanup obligation，`run.sh` 只绑定/透传并履行该 invocation 的显式 teardown，不能接管或清理其他资源。iOS Pods 由标准 `flutter build ios` 按需处理。

`--hermetic`、受管字面 `flutter run`，以及 `QWQ_CANONICAL_LAUNCH_ACTOR=app-content-uat` 的调用，走 managed/hermetic 链路：stackctl 控制面拥有源码冻结、依赖胶囊、full runtime、preflight、consumer lease、transport/receipt 与 teardown obligation，`run.sh` 只消费经验证的外层事实并代执行显式 cleanup。Prod/Release、`make app-uat`、CI 的 trust 与供应链门禁没有放宽。

- 无 `-d`：单设备自动，多设备在 TTY 显示编号选择；非 TTY typed fail closed。
- 开发直连参数仅为 `--env alpha|beta|gamma`、`--target <env>-local`、`-d/--device`、`--mode content-live|ui-only`、`-v`；其他参数数秒内 typed 拒绝并提示使用 `--hermetic`。
- 前台支持 `r` 热重载、`R` 热重启、`q` 退出；同设备重复启动会先终止既有进程再启动。
- 首次遇到已退役的 `embedded_default_package` iOS Simulator/Android receipt 时，只清理这组旧 runtime 文件一次；当前 `external_runtime_package` 状态不会被重置。
- Android emulator 使用同一 handoff 与 executor，并通过 `QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT` 只嵌入 trust envelope。alpha/beta/gamma 默认是远端 HTTPS/WSS 地址；direct/lightweight 路径不执行 `adb reverse`、不持有 lease。需要宿主机 transport 时必须走 managed/hermetic，由 stackctl 准备 receipt/lease 并只清理本 invocation owned mapping。

## 4. 人类一键开发：`make app-dev`

在仓库根运行：

```bash
make app-dev
make app-dev ENV=beta MODE=content-live
make app-dev ENV=gamma MODE=ui-only DEVICE_ID=<flutter-device-id>
```

默认 `ENV=alpha`、`MODE=content-live`。`ENV` 只接受 `alpha|beta|gamma`，`MODE` 只接受 `content-live|ui-only`。Make 只映射参数并委托 stackctl/canonical device authority，不拥有设备发现、target 扩展、交互、provenance、状态机或 receipt。

## 5. IDE canonical profile

完成 Cursor scope 激活并 Reload Window 后，在 Run and Debug 中选择：

```text
QuWoQuan: canonical launch + IDE attach
```

该 profile 通过受版本控制的本地投影执行 canonical pre-launch，再由 IDE attach attempt-scoped VM service。环境只选 Alpha/Beta/Gamma，设备与模式显式输入；不要新建第二套 Dart launch profile。

## 6. AI/自动化 UAT：`make app-uat`

该入口无交互，参数必须显式提供：

```bash
make app-uat \
  TARGETS=alpha-local,beta-local,gamma-local \
  PLATFORM=ios-simulator \
  DEVICE_ID=<flutter-device-id>
```

`TARGETS` 只能是 `alpha-local|beta-local|gamma-local` 的非空、无重复子集，禁止 Prod。`PLATFORM` 使用 stackctl 当前闭集。该入口必须使用 managed/hermetic ownership 编排 canonical raw evidence；direct `run.sh`、IDE 的 lightweight 观测或其他无 receipt 启动不能替代它，也不得提升为 promotable。

## 7. 不受支持的 raw 路径

原始 Xcode backend、原始 Gradle backend 与绝对路径真实 SDK 的 raw `flutter run` 都不属于受支持入口。一切 buildMode/buildProfile 缺少 canonical handoff/trust 时必须在构建/安装前以 `APP.LAUNCH.runtime_config_trust_missing` typed fail closed；build phase 只验证，不会创建、刷新或修复 PATH 注入、handoff 或 runtime config 投影（构建期默认供给已退役，无任何物化例外）。不得关闭 Prod trust gate。

## 8. 生命周期与证据分层

- stackctl 是 managed/hermetic runtime preparation 的 owner：管理 environment package/up/health、full runtime、内容 release/readback、consumer lease、transport receipt 与 teardown；服务就绪不等于 App 已启动。
- direct/lightweight `run.sh` 管理当前工作树的 compile/install/configure/launch 与开发观测，但不签发 `app-launch-attempt`/test-live report，不具 promotion authority；PID 存活或 VM attach 也不等于 promotable `launched`。
- 字面 `flutter run` 经 dispatcher 注入 managed intent 后复用同一执行体，但其证据来自 stackctl 外层的 receipt/lease/launch control；不能把 direct `run.sh` 的无 receipt 结果改标为 managed。`native_flutter_run` provenance 已退役。
- UAT/evidence 必须使用 managed/hermetic ownership，绑定 immutable source、strict zero-warning preflight、canonical launch receipt/safe terminal 与 raw `ReadinessCaseResult`；direct/lightweight 日志、截图、VM attach 或 warning/degraded 结果一律不可提升为 promotable。父级只读投影与旧 receipt 也不能冒充当前通过。


## 9. 开发启动验收协议

固定在实际编辑的主工作树 `quwoquan_app/` 验证；`git rev-parse --show-toplevel` 必须打印该主仓。facade 代码变化后重新执行 `make app-activate-flutter-facade FACADE_ACTION="--scope all"`，Cursor Reload Window，并分别新开一个 Cursor terminal 与一个 macOS Terminal/iTerm。

两个新终端都先确认 `which flutter` 与 `which run.sh` 指向主仓 launcher bin，再分别字面执行：

```bash
flutter run -d <ios-simulator-udid>
run.sh --env alpha -d <ios-simulator-udid>
```

一次有效验收必须同时具备：

1. 冷启动 5 分钟内、热启动 90 秒内出现 `QWQ_APP_LAUNCH_PHASE status=launched` 并保持 r/R/q attach 交互态；
2. 模拟器截图是正常首页/欢迎页，不是启动配置错误页；
3. 输出包含 `configurationState=complete`（或可证明已向 alpha gateway 发出真实请求）；
4. 修改一处可见 Dart 文案并按 `r` 后，模拟器内容变化。

连续执行两次，中间不清缓存、不重激活。contract test、facade status、receipt、服务健康数都只算回归信号，不能替代上述用户工作树的字面命令、首帧与热重载证据。任何阶段静默超过 60 秒应作为启动缺陷处理。
