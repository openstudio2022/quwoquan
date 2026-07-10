# L3：跨平台可移植架构（cross-platform-portability）

## L1 / L2 / L3 映射

| 层级 | 标识 |
|---|---|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `cross-platform-portability` |

挂树：`AppRoot -> runtime -> runtime-client-foundation -> cross-platform-portability`。

## 目标

为 quwoquan_app 未来接入**鸿蒙（OpenHarmony / HarmonyOS NEXT）**与**独立宽屏 Web** 做提前准备，使业务层零改动或最小改动即可移植。核心原则 **能力优先、平台后置**：业务/页面只消费能力契约（`PlatformCapabilities`）与体验一致性契约，平台差异收口到防腐层（`lib/core/platform/**`）。

执行军规见 [.cursor/rules/14-cross-platform-portability.mdc](../../../../../.cursor/rules/14-cross-platform-portability.mdc)。

## 范围

负责：

- 定义平台防腐层（能力契约 + 平台枚举 + 文件网关 + 原生桥）的结构与职责。
- 定义产品/设计体验一致性契约（同源项 vs 允许差异项）。
- 定义鸿蒙双 SDK 策略、三方包兼容矩阵、分阶段里程碑与决策点。
- 定义 Web 独立宽屏壳设计与 blocker 清单。
- 定义跨平台测试 profile 与门禁证据口径。

不负责：

- 实现鸿蒙 `ohos/` 原生工程、Web 全量宽屏壳、RTC/来电的平台落地（各自独立里程碑）。
- 替代 `contracts/metadata/**` 的字段、错误码、路由、surface 唯一真相源。
- 一次性重写存量 32 个 `dart:io` 直接引用文件（只建收口入口 + 基线只减不增）。

## 三层职责模型

```text
业务/页面关心：能力是否可用、体验应该如何降级
防腐层关心：当前平台如何实现这些能力       —— lib/core/platform/**
平台原生层关心：Android / iOS / OHOS / Web 的具体 API
```

| 关注点 | 唯一入口（真相源） | Provider |
|---|---|---|
| 能力是否可用 | `PlatformCapabilities`（`platform_capabilities.dart`） | `platformCapabilitiesProvider` |
| 平台标识（仅装配/可观测） | `AppPlatform`/`currentAppPlatform`（`platform_target.dart`） | `platformTargetProvider` |
| 文件/路径/目录 | `FileStorageGateway`（`file_storage_gateway.dart`） | `fileStorageGatewayProvider` |
| 原生通道 | `NativeBridge` 系列（`native_bridge.dart`） | `assistantLocalContextBridgeProvider` 等 |
| 失败/不可用 | `PlatformCapabilityUnavailableException.runtimeFailure` | — |

## 能力契约（PlatformCapabilities）

能力位（最小集，可扩展）：

| 能力位 | 含义 | mobile | web | ohos(初始) | desktop |
|---|---|:--:|:--:|:--:|:--:|
| `hasLocalFileSystem` | 本地随机读写文件系统 | ✓ | ✗ | ✓ | ✓ |
| `mediaLibrary` | 系统相册访问/保存 | ✓ | ✓ | ✓ | ✗ |
| `camera` | 实时相机采集 | ✓ | ✓ | ✓ | ✗ |
| `realtimeCommunication` | WebRTC/LiveKit | ✓ | ✓ | ✗ | ✓ |
| `incomingCallUi` | 系统来电/CallKit/VoIP | ✓ | ✗ | ✗ | ✗ |
| `nativeVideoEditing` | 原生裁剪/静音/导出 | ✓ | ✗ | ✗ | ✗ |
| `secureStorage` | 硬件级安全存储 | ✓ | ✗ | ✓ | ✓ |
| `backgroundAudio` | 后台/锁屏音频 | ✓ | ✗ | ✓ | ✓ |
| `wideScreenLayout` | 宽屏多列壳 | ✗ | ✓ | ✗ | ✓ |
| `promotesAppInstall` | 运行时展示 App 安装提示 | ✗ | ✓ | ✗ | ✗ |
| `oneTapLogin` | 运营商/厂商一键登录 | ✓ | ✗ | ✗ | ✗ |

> 高风险能力（RTC、来电、原生视频编辑）在新增平台默认关闭，随各自里程碑逐步打开。`CapabilityProfile` 是测试注入与平台装配的共同来源。

## 产品与设计体验一致性契约（Product & Design Consistency）

为保证「一套体验、多平台一致、维护成本低」：

**必须跨平台同源（禁止平台私有分叉）**：

- 信息架构（IA）、`route_id`、`surface_id`、`operation_id`。
- 主任务流、埋点语义、文案 key。
- 空态、错误态、权限态展示语义（对齐 [error-permission-display-semantics](../error-permission-display-semantics/spec.md) 与 `07-error-permission-semantics`）。

**仅允许差异**：

- 布局密度、导航壳形态（移动底栏 vs 宽屏侧栏/Rail）。
- 内容列数、可用横向空间利用。
- 悬停、快捷键、右键等宽屏增强（移动端无则无，不改变任务流）。

**降级一致性**：能力不可用时（Web 无本地文件、鸿蒙缺相册缓存 API、RTC 未启用），复用同一套权限/错误/降级展示语义，禁止各平台自造提示。

**设计走 token**：宽屏适配只能通过 `AppSpacing` 断点 + `responsiveValue` 进入，禁止页面私有断点（`14` R-XP7 门禁拦截）。

## Web 内容优先体验规格（布局 + 安装提示）

### 体验目标

Web 首屏以内容消费为主，承担「可读、可看、可转发」的轻量入口；高频互动、创作、RTC、来电、原生视频编辑等能力优先引导到 App。Web 不复制一套产品流程，仍复用同一 IA / route / surface / 埋点语义，只在布局密度、导航壳与安装提示上做差异。

公开内容入口的完整闭环规格（Markdown 真相源、SEO HTML、站外 HTTPS 分享、PC Pinterest 体验）见 [`public-content-web-entry/spec.md`](../public-content-web-entry/spec.md)。本文件只保留跨平台壳层与能力防腐约束；SEO HTML 不能由 Flutter Web 单独承担，必须从同一 `articleMarkdown` 派生公开 HTML 投影。

### 断点语义扩展

`AppSpacing` 增加 `wideBreakpoint=1024` 与 `responsiveWideValue`，形成四级语义：

| 语义 | 阈值 | 典型形态 |
|---|---|---|
| `compact` | `< 360` | 小屏手机 |
| `regular` | `360–599` | 常规手机 |
| `expanded` | `600–1023` | 大屏/折叠/平板竖屏 |
| `wide` | `>= 1024` | Web/桌面宽屏（内容主列 + 侧栏/Rail 预留） |

内容主列使用 `webContentMaxWidth=1120`，避免 PC 上无限拉宽造成阅读疲劳。所有宽屏适配必须经 `AppSpacing` token，不得页面内手写断点。

### 壳分型（当前落地 + 后续草案）

```text
MainAppShell
├── capabilities.promotesAppInstall == true -> WebAppInstallBanner（顶部安装提示）
├── capabilities.wideScreenLayout == false  -> 移动壳（现有 bottom_navigation）
└── capabilities.wideScreenLayout == true   -> 内容主列 maxWidth=AppSpacing.webContentMaxWidth
                                                后续演进 NavigationRail / 侧栏
```

约束：

- 复用现有 `go_router` 路由与 metadata `route_id`，**不为 Web 新建第二套 IA**。
- 壳切换依据 `platformCapabilitiesProvider.wideScreenLayout` + 宽度断点，**不依据 `AppPlatform`**。
- 导航项、选中态语义与移动端同源（对齐 `07-ios-native-ux` 几何稳定）。

### 顶部下载 App 提示

入口：`lib/app/shell/web_app_install_banner.dart`，由 `PlatformCapabilities.promotesAppInstall` 控制。Native 不展示，Web 展示。

| 打开设备 | 布局 | 行为 |
|---|---|---|
| 手机/Pad Web | 72px 顶部提示条 | 主按钮「下载 App」打开 `WEB_APP_MOBILE_DOWNLOAD_URL`；次按钮「分享」走系统分享，把 `WEB_APP_SHARE_INSTALL_URL` 传给微信/好友安装 |
| PC Web | 56px 顶部提示条 | 展示 `iPhone / iPad` 与 `Android / 鸿蒙` 两个安装包入口；提供「分享安装页」便于发到手机或微信继续安装 |

下载 URL 不在代码写死，走 `CloudRuntimeConfig` + `--dart-define`：

- `WEB_APP_MOBILE_DOWNLOAD_URL`（默认 `/download/mobile`）
- `WEB_APP_DESKTOP_DOWNLOAD_URL`（默认 `/download/desktop`）
- `WEB_APP_SHARE_INSTALL_URL`（默认 `/download`）
- `WEB_APP_IOS_DOWNLOAD_URL`（默认 `/download/ios`）
- `WEB_APP_ANDROID_DOWNLOAD_URL`（默认 `/download/android`）

文案、颜色、间距、圆角、内容宽度全部走 `UITextConstants` / `AppColors` / `AppSpacing` / `AppTypography` 语义 token。

### Web blocker 清单（落地前必须处理）

| Blocker | 现状 | 策略 |
|---|---|---|
| `dart:io` 散落 ~32 文件 | import 即破坏 web | 经 `FileStorageGateway` 收口；门禁只减不增 |
| `sqflite` | web 默认不可用 | `sqflite_common_ffi_web` 或 IndexedDB 适配层 |
| `flutter_secure_storage` | web 能力受限 | 降级到受限实现 + `secureStorage` 能力位关 |
| RTC/媒体 | web 行为差异 | `realtimeCommunication`/`camera` 能力位 + 降级 |
| `photo_manager`/`image_picker` | web 行为差异 | 能力位 `mediaLibrary` + web picker 降级 |

## 鸿蒙 Flutter/Dart 与三方包适配策略

### 双 SDK

- iOS/Android：Google Flutter（`pubspec.yaml` 要求 `>=3.44.0`）。
- 鸿蒙：社区 Flutter-OH SDK（[openharmony-sig/flutter_flutter](https://gitcode.com/openharmony-sig/flutter_flutter)），独立 `FLUTTER_ROOT`、独立 CI job。
- **禁止**用一个 `pubspec.yaml` 同时满足两套 SDK 的全部约束；OH 依赖替换走独立 `configs/ohos_dependency_overrides.yaml`（Git 依赖指向 [openharmony-tpc/flutter_packages](https://gitcode.com/openharmony-tpc/flutter_packages) `br_<库>-v<版本>_ohos` 分支）。

### 三方包兼容矩阵（字段化）

字段：`pure_dart` / `web_support` / `ohos_support` / `replacement` / `fallback_behavior` / `owner` / `risk_level`。

| 包 | ohos | web | replacement / fallback | risk |
|---|---|---|---|---|
| `photo_manager` | 已有 `vendor/.../ohos/` | 行为差异 | 能力位降级 | 中 |
| `path_provider`/`shared_preferences`/`url_launcher`/`connectivity_plus`/`webview_flutter` | 社区 OH 版 | 多数 OK | Git 依赖替换 | 低 |
| `simple_icons`/`cupertino_icons`/`fluentui_system_icons` | 纯 Dart 字体包（pure_dart=yes） | yes（字体随包内置） | 无需 replacement，图标随包打包，无运行时 fallback | 低 |
| `sqflite` | 查社区版 | `ffi_web`/IndexedDB | 收口存储层 | 中 |
| `flutter_secure_storage` | 待评估 | 受限 | `secureStorage` 能力位 | 中 |
| `flutter_webrtc` | `fluttertpc_flutter_webrtc` | web 原生 | 能力位 + flag | 高 |
| `livekit_client` | `fluttertpc_livekit_client` | web | 能力位 + flag | 高 |
| `flutter_callkit_incoming` | 鸿蒙 VoIP 重写 | 不适用 | `incomingCallUi` 关闭 | 高 |

原则：能用社区 OH 版/Git 依赖就不自行 fork；高风险包独立里程碑，不阻塞只读/社交文字主路径。

### 决策点（需产品/架构拍板）

1. OH 首版是否允许 Dart/Flutter 略低于 3.44（Flutter-OH 滞后官方约 4 个月）。
2. MVP 范围是否接受首版无 RTC、无一键登录、视频编辑降级。
3. 发布渠道：AppGallery 与 Android 包是否并行、版本号对齐策略。

## 跨平台测试 profile

测试原则：**同一行为契约，多平台实现**，不复制三套测试。

- 三套 profile：`CapabilityProfile.mobile|web|ohos`，经 `platformCapabilitiesProvider` override 注入。
- 同一批 Provider/Repository/导航/错误态/降级 行为契约测试，在不同 profile 下参数化运行。
- 平台测试只测差异边界：Web 无本地文件降级、鸿蒙缺相册缓存 API、RTC/视频编辑能力关闭时入口隐藏与提示。
- 本次交付：本设计 + 1 个示例骨架 `quwoquan_app/test/local_contract/core/platform/platform_capabilities_profile__local_contract_test.dart`（capability 驱动的入口降级断言）。

## 分阶段里程碑

- 阶段0 POC：Flutter-OH 环境 + `flutter create --platforms=ohos .` + path_provider/shared_preferences OH 版空壳 HAP；Web `flutter run -d chrome` 跑通骨架。
- 阶段1：核心只读路径（发现/详情/阅读/设置）双平台跑通，RTC/创作 feature flag 隔离。
- 阶段2：存储与 UGC（sqflite/Hive/photo_manager/image_picker/permission）。
- 阶段3：聊天与语音（record/just_audio/audio_session）。
- 阶段4：RTC/来电独立里程碑。
- 阶段5：工程化与上架（OH 构建脚本、签名、AppGallery、灰度回滚）。

## 测试与门禁证据

| 证据 | 内容 |
|---|---|
| local_contract contract | `verify_lib_dart_io_budget.py`、`verify_lib_platform_check_isolation.py` 基线只减不增 |
| local_contract widget | capability profile 驱动的入口降级契约测试（示例骨架） |
| 静态 | `flutter analyze quwoquan_app/lib/`、`verify_dart_semantic.py` 不回退 |
| 串联 | `bash quwoquan_ops/gate/gate_repo.sh --scope app` |

## 验收

- 防腐层 `lib/core/platform/**` 存在且 `flutter analyze` 通过。
- 业务层无新增 `dart:io` / 裸平台判断 / 裸 channel（门禁基线只减不增）。
- 端侧 `platform()` 可返回 `ohos`/`web`；云侧枚举登记走 metadata-first。
- 军规 14 生效并串联 `make gate`。
- 本 spec 的体验一致性、Web 壳、鸿蒙策略、测试 profile 章节齐备。
