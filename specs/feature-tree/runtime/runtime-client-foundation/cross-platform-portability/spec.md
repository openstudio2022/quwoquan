# L3 Story：跨平台可移植架构（cross-platform-portability） (`cross-platform-portability`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

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

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 跨平台能力防腐层成立

- GIVEN 业务页面需要判断文件、相册、相机、RTC、宽屏、安装提示等能力。
- WHEN 页面或服务读取平台能力。
- THEN 调用方只消费 PlatformCapabilities、AppPlatform、FileStorageGateway 或 NativeBridge 防腐层。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

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
