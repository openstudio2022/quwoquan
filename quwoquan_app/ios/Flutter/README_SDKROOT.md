# iOS SDKROOT 配置说明

## 问题描述
在 Flutter 3.38+ 版本中，使用 native_assets 功能时可能会遇到以下错误：
```
Target native_assets required define SdkRoot but it was not provided
```

### 与 Xcode / 全量构建无关时
该报错常见于 **`flutter run` 热重载路径**：工具链传给 native_assets 的环境缺少 `SdkRoot`（与全量 `flutter build` 不同）。Flutter 已在 master 修复（见 [flutter/flutter#180603](https://github.com/flutter/flutter/issues/180603) 及关联 PR）。

**推荐**：将 Flutter SDK 升级到已包含上述修复的稳定版 / beta。

**临时规避**（可能影响依赖 native assets 的 FFI 包，慎用）：
```bash
flutter config --no-enable-native-assets
```
恢复默认：
```bash
flutter config --enable-native-assets
```

## 本仓库当前修复方案
除了保留 Xcode 工程侧的 `SDKROOT` 防御配置外，本仓库额外锁定了
不会触发 `sqlite3` native assets 的依赖组合：

- `sqflite_common_ffi: 2.3.7+1`
- `sqlite3: 2.9.4`

原因是当前 Flutter stable 的 iOS `flutter run` / hot restart 链路里，
即使工程侧已经写了 `SDKROOT`，只要依赖图里还包含 `native_assets`
构建链，仍可能继续报 `SdkRoot` 缺失。

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
- 如果未来升级到已完全修复该问题的 Flutter stable，可重新评估是否移除
  `sqflite_common_ffi/sqlite3` 版本锁定
- 不要删除这些配置，否则可能会再次出现 SdkRoot 错误
