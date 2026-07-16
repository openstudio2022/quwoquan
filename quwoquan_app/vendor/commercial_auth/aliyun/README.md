# 阿里云号码认证客户端 SDK 注入

阿里云 PNVS 客户端 SDK 只能从已登录的号码认证控制台下载，仓库和公共依赖源不能代替该授权下载。

受控构建步骤：

1. 从阿里云号码认证控制台下载同一发布版本的 Android 与 iOS SDK。
2. Android 的官方 `.aar`/`.jar` 放入 `android/`；Gradle 会通过受控 `fileTree` 装配。
3. iOS 的 `ATAuthSDK.framework`/`.xcframework` 及官方依赖放入 `ios/`，再执行 `pod install`。
4. 构建密钥系统注入 `QWQ_ALIYUN_PNVS_SECRET_INFO`。它是客户端认证方案密钥，不得与服务端 `ALIYUN_DYPNS_ACCESS_KEY_SECRET` 混用。
5. 缺少任一二进制或密钥时，`quwoquan/auth/one_tap` 必须返回不可用并回退短信验证码。

SDK 包、方案密钥与服务端 AccessKey 均不得写入 Git。发布流水线必须校验供应商包 SHA-256 与批准清单一致。
