# iOS SDKROOT 配置说明

## 问题描述
在 Flutter 3.38+ 版本中，使用 native_assets 功能时可能会遇到以下错误：
```
Target native_assets required define SdkRoot but it was not provided
```

### 与 Xcode / 全量构建无关时
该报错常见于 **`flutter run` 热重载路径**：工具链传给 native_assets 的环境缺少 `SdkRoot`（与全量 `flutter build` 不同）。Flutter 已在 master 修复（见 [flutter/flutter#180603](https://github.com/flutter/flutter/issues/180603) 及关联 PR）。

**推荐**：将 Flutter SDK 升级到已包含上述修复的稳定版 / beta（本仓库目标 Flutter >= 3.47）。

**临时规避**（可能影响依赖 native assets 的 FFI 包，慎用）：
```bash
flutter config --no-enable-native-assets
```
恢复默认：
```bash
flutter config --enable-native-assets
```

## 本仓库 sqflite 策略（2026-06）

移动端 App 包使用 **`sqflite` 原生插件**（`lib/` 仅 `import package:sqflite/sqflite.dart`），主业务代码不直接依赖 `sqlite3`。

VM/CI 单测使用：

- `sqflite_common_ffi ^2.4.0+3`
- `sqlite3 3.5.1`（由上游传递解析）

当前验证结论：

- iOS Simulator 构建可通过
- Android Debug 构建可通过
- 相关 sqflite 单测可通过

当前仓库策略：

- `quwoquan_app` 主运行链路不依赖外部下载 `sqlite3` native assets。
- 根 `pubspec.yaml` 已通过 `hooks.user_defines.sqlite3.source=system` 固定到系统 SQLite，
  避免 `flutter run` / Xcode build 因 GitHub release 下载抖动而阻断。
- `sqflite_common_ffi` 仅用于主机侧 VM/CI 单测；移动端运行仍使用 `sqflite` 原生插件。

## 本地依赖纯度策略（2026-06-22）

- `quwoquan_app/run.sh` 与 `quwoquan_app/scripts/env/run_flutter_test_guarded.py`
  统一使用 `flutter pub get --offline`，并以 `flutter run --no-pub` 启动，禁止
  启动链偷偷联网补依赖。
- iOS 侧要求 `ios/Podfile.lock` 与 `ios/Pods/Manifest.lock` 完全一致；若 drift，
  启动脚本直接 fail-closed，而不是在运行时尝试修复 pod graph。
- Android 自定义上游 AAR（`webrtc-sdk`、`audioswitch`、`livekit noise`）已固定
  到 `quwoquan_app/vendor/android_artifacts/`，不再允许通过 GitHub / JitPack /
  自定义 Maven 在编译时下载。
- 仓库级门禁：`python3 quwoquan_ops/gate/verify_local_dependency_purity.py`。

## 防御配置（Xcode 工程侧）
已在以下 xcconfig 文件中明确设置了 SDKROOT：
- `Debug.xcconfig`
- `Release.xcconfig`
- `Profile.xcconfig`

## 配置内容
每个 xcconfig 文件都包含：
```
SDKROOT = iphoneos
SUPPORTED_PLATFORMS = iphoneos iphonesimulator
```

## 验证
运行以下命令验证配置：
```bash
xcrun --show-sdk-path --sdk iphoneos
xcrun --show-sdk-version --sdk iphoneos
```

## 注意事项
- 这些配置会覆盖默认设置，确保构建时使用正确的 SDK
- 不要删除这些配置，否则可能会再次出现 SdkRoot 错误
