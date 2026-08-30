# iOS 代码签名配置说明

## 问题
"No development certificates available to code sign app for device deployment"

## 解决方案

### 方案 1: 使用 iOS 模拟器（推荐用于开发）
模拟器不需要开发者签名证书，但仍必须物化 App runtime trust envelope。使用 canonical launcher：
```bash
./quwoquan_app/run.sh -d <simulator-udid>
```

如需在 Cursor 新终端执行字面 `flutter run`，先在仓库根运行
`make app-activate-flutter-facade`，Reload Window，打开新终端并确认
`command -v flutter` 指向 workspace facade，再执行 `flutter run -d <simulator-udid>`。

### 方案 2: 配置自动签名（用于真机测试）
1. Xcode 只用于配置签名，不是本仓库的直接启动入口。打开项目：
   ```bash
   open ios/Runner.xcworkspace
   ```

2. 在 Xcode 中：
   - 选择 Runner 项目
   - 选择 Runner target
   - 进入 "Signing & Capabilities" 标签
   - 勾选 "Automatically manage signing"
   - 选择你的 Apple ID 团队（如果没有，需要先登录）

3. 如果使用个人 Apple ID：
   - 在 Xcode 中登录：Preferences > Accounts > 添加 Apple ID
   - Xcode 会自动创建开发证书和配置文件

### 方案 3: 修改 Bundle ID（如果当前 ID 已被使用）
如果 `com.example.quwoquanApp` 已被使用，需要修改为唯一的 Bundle ID：
- 在 Xcode 中修改，或
- 修改 `ios/Runner.xcodeproj/project.pbxproj` 中的 `PRODUCT_BUNDLE_IDENTIFIER`

## 当前配置
- Bundle ID: `com.example.quwoquanApp`
- 签名方式: Automatic
- 开发团队: 未设置（需要在 Xcode 中配置）

## 注意事项
- 真机测试需要有效的 Apple Developer 账户（免费个人账户即可）
- 模拟器测试不需要任何证书
- 原始 `flutter run`、`flutter run --no-pub` 或 Xcode Run 会绕过 runtime trust handoff 并被构建门禁拒绝
- 如果只是开发测试，建议使用模拟器和 canonical launcher
