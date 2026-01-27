# iOS SDKROOT 配置说明

## 问题描述
在 Flutter 3.38+ 版本中，使用 native_assets 功能时可能会遇到以下错误：
```
Target native_assets required define SdkRoot but it was not provided
```

## 解决方案
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
- 如果更新 Xcode 或 Flutter 版本，可能需要重新验证这些配置
- 不要删除这些配置，否则可能会再次出现 SdkRoot 错误
