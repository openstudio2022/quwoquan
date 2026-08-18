# 跨平台可移植军规（鸿蒙 + Web）

目标：让 `quwoquan_app` 在接入鸿蒙（OpenHarmony/HarmonyOS NEXT）与独立宽屏 Web 时，业务层
零改动或最小改动。核心原则是 **能力优先、平台后置**：业务问「能力是否可用 / 如何降级」，
不问「是不是 Web/鸿蒙」。

规划与设计细节见
`specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md`。
视觉断点与宽屏表面规则归 ux，见
[../../ux/references/responsive-surfaces.md](../../ux/references/responsive-surfaces.md)。

## 三层职责（不可越层）

```text
业务/页面关心：能力是否可用、体验应该如何降级
防腐层关心：当前平台如何实现这些能力 —— lib/runtime/platform/**
平台原生层关心：Android / iOS / OHOS / Web 的具体 API
```

`lib/runtime/platform/**` 是平台能力防腐层的**唯一物理位置**；业务对象、页面、其他 runtime
模块与 design system 只依赖这里公开的 capability/bridge/gateway，不得重新建立
`lib/core/platform/**` 或领域私有平台判断入口。

| 关注点 | 唯一入口 | Provider |
|---|---|---|
| 能力是否可用 | `PlatformCapabilities` | `platformCapabilitiesProvider` |
| 平台标识（仅装配/可观测） | `AppPlatform` / `currentAppPlatform` | `platformTargetProvider` |
| 文件/路径 | `FileStorageGateway` | `fileStorageGatewayProvider` |
| 原生通道 | `NativeBridge` 系列接口 | `assistantLocalContextBridgeProvider` 等 |

## 必守（GATE_BLOCK）

- **R-XP1 能力优先（最高原则）**：业务层（`lib/service/**`、`lib/design_system/**`，以及
  `lib/runtime/**` 中除 `lib/runtime/platform/**` 之外的全部目录）禁止基于平台做体验分叉。
  需要平台差异时，**先在 `PlatformCapabilities` 登记能力位**，业务只读能力位决定
  「展示入口 / 如何降级」。
- **R-XP2 平台判断单一真相源**：业务层禁止裸用 `Platform.isAndroid/isIOS/...`、
  `Platform.operatingSystem`、`kIsWeb`。平台判断只允许出现在 `lib/runtime/platform/**`。
- **R-XP3 dart:io 收口**：业务层禁止 `import 'dart:io'`；文件/路径/目录能力走
  `FileStorageGateway`。存量已清零、allowlist 已退役，**命中即 BLOCK，不接受豁免登记**。
- **R-XP4 原生能力走防腐接口**：业务层禁止**新增**裸 `MethodChannel` / `EventChannel` /
  `BasicMessageChannel`。必须经 `NativeBridge` 抽象：抽象接口 + `MethodChannel*` 实现 +
  未实现平台的 `Unsupported*` 实现返回结构化「不可用」，禁止 crash；由
  `platformCapabilitiesProvider` 决定装配哪一个。
- **R-XP5 缺失即一致降级**：任何平台特有能力（相机、相册、RTC、来电、视频编辑、安全存储、
  后台音频）必须有 capability 探测 + 降级路径；降级的权限/错误/提示语义必须遵循所属服务
  `errors.yaml` 与 App runtime mapper。禁止「仅某平台可用」的硬编码直连。

## 必守（PR_WARN / 评审拦截）

- **R-XP6 产品体验同源**：禁止平台私有产品流程。IA、`route_id`、`surface_id`、
  `operation_id`、主任务流、埋点语义、空态/错误态/权限态、文案 key 必须跨平台一致。
  差异仅允许出现在：布局密度、导航壳形态（底栏 vs 侧栏/Rail）、内容列数、
  悬停/快捷键/右键等宽屏增强。
- **R-XP8 三方包矩阵登记**：新增/升级依赖前必须评估 `android/ios/ohos/web` 四平台可用性，
  结论按字段记入 spec 插件矩阵（`pure_dart`/`web_support`/`ohos_support`/`replacement`/
  `fallback_behavior`/`owner`/`risk_level`）。优先复用社区 OH 版/Git 依赖，禁止随意 fork；
  `vendor/plugins/**` 新增 pin 必须说明 OH/Web 策略。
- **R-XP9 测试原则一致**：跨平台行为测试用 capability profile 驱动**同一批**行为契约
  （`CapabilityProfile.mobile|web|ohos` 经 `platformCapabilitiesProvider` override 注入）；
  禁止为平台复制整套测试。平台测试只测**差异边界**。

## 鸿蒙 / Web 构建约束

- **双 SDK**：iOS/Android 用 Google Flutter；鸿蒙用社区 Flutter-OH SDK，独立 `FLUTTER_ROOT`
  与独立 CI job。OH 依赖替换走独立 overrides 文件，不污染主 `pubspec`。
- **平台枚举 contracts-first**：端侧 `CloudRequestHeaders.platform()` 可先返回 `ohos`/`web`，
  但云侧 `X-Client-Device-Platform` 枚举必须先改其所属服务 contract，再 verify/codegen。
- **高风险能力独立里程碑**：`flutter_webrtc` / `livekit_client` /
  `flutter_callkit_incoming` 在鸿蒙/Web 的适配不得阻塞只读与社交文字主路径；
  通过能力位 + feature flag 隔离。

## 门禁

```bash
python3 quwoquan_app/scripts/runtime/platform/verify_lib_dart_io_budget.py
python3 quwoquan_app/scripts/runtime/platform/verify_lib_platform_check_isolation.py
```

两者已串联 `make gate` → `quwoquan_ops/gate/gate_repo.sh` 的 `run_app` 阶段。
第二个脚本无 allowlist：防腐层两段之外命中即 BLOCK。
