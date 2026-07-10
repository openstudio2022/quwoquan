# quwoquan_app scripts

App 脚本只承载 App 自治的构建、端侧验证、设备辅助和静态门禁。环境拓扑、证书、网络、发布编排和跨域调度归 `quwoquan_ops/`。

```text
_common/   App 脚本共享 helper
auth/      登录与鉴权契约门
chat/      App chat UI/Mock/Remote 一致性门
content/   内容 UI 与阅读器边界门
device/    本地设备启动、停止和首帧诊断
env/       App 四环境配置与包纯度门
fonts/     App 字体资源校验
gamma/     gamma-local App 侧验证入口
ios/       iOS 本地开发日志辅助
media/     App 媒体资源校验
runtime/   App 静态架构与 runtime 契约门
settings/  设置页规范门
web/       Web 离线资源校验
cli.py     App 薄 CLI 入口
```

禁止在本目录恢复 Figma 同步工具链、个人助手脚本或第二套环境编排入口。
