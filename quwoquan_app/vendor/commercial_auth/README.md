# 商用登录原生 SDK 固定清单

本目录只存放无法通过官方包仓稳定获取的官方二进制。所有 App ID 由构建密钥系统注入，目录内禁止出现私钥、App Secret、access token 或 auth code。

| SDK | 固定版本 | 来源 | Android | iOS | OHOS | Web | 缺失时降级 |
|---|---:|---|---|---|---|---|---|
| 微信 OpenSDK | Android 6.8.34 / iOS 2.0.5 | Maven Central / `WechatOpenSDK-XCFramework` | 支持 | 支持 | 不装配 | 不装配 | 能力位关闭，入口隐藏 |
| 支付宝 SDK | Android 15.8.42 / iOS 15.8.40.1 | Maven Central / 支付宝官方下载 | 支持 | 支持 | 后续使用 `@cashier_alipay/cashiersdk` | 不装配 | 能力位关闭，入口隐藏 |
| QQ OpenSDK Lite | Android 3.5.19 / iOS 3.6.20 | QQ 开放平台官方下载 | 支持 | 支持 | 不装配 | 不装配 | 能力位关闭，入口隐藏 |
| 阿里云号码认证 | 由受控构建缓存注入 | 阿里云号码认证控制台 | 支持 | 支持 | 不装配 | 不装配 | 一键登录能力关闭，回退手机号验证码 |

QQ Android JAR SHA-256：
`9d57fe61ff9026d34ac84bc63dc719f61da6aa40533a299cc6f73d4ce9df7af8`

二进制升级必须同时更新本文件、所属对象的外部 capability 契约、本地契约测试和四环境包纯度门禁。
