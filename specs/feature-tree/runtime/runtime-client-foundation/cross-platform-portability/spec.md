# L3 Story：跨平台可移植架构（cross-platform-portability） (`cross-platform-portability`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-006](../design.md#dec-006)

## 1. 用户价值

作为使用不同受支持平台的用户，
我希望在 iOS、Android 与 Web 获得同一业务能力和可解释的平台降级，
从而不会因平台差异遇到静默缺失或错误交互。

## 2. 范围与非目标

### In Scope

- 平台能力防腐层。
- 体验一致性契约。
- Web 宽屏和安装提示基线。
- 跨平台测试 profile 与门禁证据口径。
- iOS / Android 可安装操作系统下限。

### Out of Scope

- 鸿蒙原生工程。
- Web 全量宽屏壳。
- RTC/来电/原生视频编辑的平台实现。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 跨平台能力防腐层成立

- 业务层不出现直接平台分支：裸平台判断、裸原生通道与文件系统直连只允许存在于平台能力防腐层，业务层存量为零且不接受豁免名单。
- 业务层读取文件、相册、相机、RTC、宽屏与安装提示等能力时，只消费 PlatformCapabilities、AppPlatform、FileStorageGateway 或 NativeBridge。
- 不支持的能力通过统一 RuntimeFailure 或能力不可用语义降级。

<a id="req-002"></a>
### REQ-002 禁止：用一个 `pubspec.yaml` 同时满足两套 SDK 的全部约束

- **禁止**用一个 `pubspec.yaml` 同时满足两套 SDK 的全部约束；OH 依赖替换走独立 `configs/ohos_dependency_overrides.yaml`（Git 依赖指向 openharmony-tpc/flutter_packages `br_<库>-v<版本>_ohos` 分支）。

<a id="req-003"></a>
### REQ-003 iOS 可安装下限为 16.0，满五年才允许抬升

- iOS 工程的 `platform :ios` 与 `IPHONEOS_DEPLOYMENT_TARGET` 必须同为 **16.0**。
- 不得在 iOS 16.0 正式发布未满五年时把该下限抬到 16.0 以上。
- 满五年后抬升是许可，不是自动义务；抬升须同步改 Podfile、Xcode 工程与本要求。
- 本要求不改变 Product Ops 的 App Build minimum。Android 安装下限见 REQ-004。

<a id="req-004"></a>
### REQ-004 Android 可安装下限跟随 Flutter SDK，且对应系统必须已满五年

- Android 工程 `defaultConfig.minSdk` 必须写 `flutter.minSdkVersion`，不得人为写死更高 API。
- 解析出的 Flutter `minSdk` 对应 Android 正式发布必须已满五年；未满五年时不得跟随 SDK 上浮。
- 本要求不改变 `targetSdk` / `compileSdk`，也不改变 Product Ops 的 App Build minimum。

<a id="req-005"></a>
### REQ-005 跨平台产品语义、依赖评估与行为测试同源

- 受支持平台共用 IA、route/surface/operation ID、主任务流、埋点、空态、错误态、权限态和文案 key。平台差异只允许落在布局密度、导航壳、内容列数及悬停/快捷键等增强，不得复制产品流程。
- 新增或升级平台依赖前，目标 Feature spec/design 必须声明 Android、iOS、OHOS、Web 的支持、替代、降级、owner 与风险；该事实不进入全局角色 reference 或第二套插件 registry。
- 同一业务行为由 capability profile 驱动同一批合同；平台专属测试只验证 native adapter、构建和差异边界，不复制整套业务验收。

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 跨平台能力防腐层成立

- GIVEN 业务页面需要判断文件、相册、相机、RTC、宽屏、安装提示等能力。
- WHEN 页面或服务读取平台能力。
- THEN 调用方只消费 PlatformCapabilities、AppPlatform、FileStorageGateway 或 NativeBridge 防腐层。

<a id="gwt-002"></a>
### GWT-002 iOS 安装下限锁定 16.0

- GIVEN 当前 App iOS 工程与 [L2 DEC-003](../design.md#dec-003)。
- WHEN 读取 `Podfile` 的 `platform :ios` 与 `Runner.xcodeproj` 的 `IPHONEOS_DEPLOYMENT_TARGET`。
- THEN 两处均为 `16.0`。
- AND 不存在把 iOS 下限声明为高于 16.0 的工程设置。

<a id="gwt-003"></a>
### GWT-003 Android 安装下限跟随 Flutter 且满五年

- GIVEN 当前 App Android 工程与 [L2 DEC-006](../design.md#dec-006)。
- WHEN 读取 `android/app/build.gradle.kts` 的 `defaultConfig.minSdk`，并解析当前 Flutter SDK 的 `minSdkVersion`。
- THEN 工程声明为 `flutter.minSdkVersion`。
- AND 解析出的 API 对应 Android 正式发布已满五年。

<a id="gwt-004"></a>
### GWT-004 跨平台产品语义与 capability-profile 测试同源

- GIVEN 同一业务能力运行在两个受支持平台，或引入一项平台相关依赖。
- WHEN 解析平台能力、产品 surface 与测试计划。
- THEN route/surface/operation、终态和文案保持同源，依赖矩阵具有明确降级，且同一行为合同由 capability profile 驱动而不是按平台复制。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-006](../design.md#dec-006)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 手势/返回策略仍按 TargetPlatform 分叉，未收口到能力位

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍有 `lib/runtime/shell/navigation/native_back_navigation.dart` 与
  `lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_presentation.dart`
  消费 `defaultTargetPlatform` / `TargetPlatform.*` 决定返回手势与沉浸式滑动策略（约 13 处）。
  这是「能力优先」军规的残留分叉：新平台（ohos/web 宽屏）接入时需要逐处评估 OS 判断，
  而不是翻一个能力位。`AppPlatform == web` 体验分叉已清零（welcome 已改 `startupWelcomeFlow` 能力位），
  且门禁 `verify_lib_platform_check_isolation.py`
  已新增 `app_platform_experience_branch` 扫描（装配层豁免 `runtime/di`、`runtime/shell/startup`）。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效——`PlatformCapabilities`
  登记导航/手势策略能力位（如 `edgeBackGesture` / `immersiveVerticalSwipe`），
  两个文件改为消费能力位；门禁扩展 `TargetPlatform` 业务层扫描且命中为 0。

<a id="open-002"></a>
### OPEN-002 跨平台产品语义与 capability-profile 合同尚缺直接证据

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺覆盖 route/surface/operation 同源、Feature 内依赖矩阵和同一行为 capability-profile 驱动的直接合同；旧 Review reference 不再作为证据或事实 owner。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。
