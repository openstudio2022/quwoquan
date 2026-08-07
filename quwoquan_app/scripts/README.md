# quwoquan_app scripts

App 脚本只承载 App 自治的构建、端侧验证、设备辅助和静态门禁。环境拓扑、证书、网络、发布编排和跨域调度归 `quwoquan_ops/`。

```text
_common/              App 脚本共享 helper
content_service/      内容域服务门（与 lib/service/content_service 对齐）
chat_service/         会话域服务门（与 lib/service/chat_service 对齐）
tag_service/          标签域服务门
user_service/         用户域服务门
runtime/
  architecture/       布局与架构棘轮
  auth/               登录、鉴权与权限契约
  cloud/              云边界与 Remote 纯度
  codegen/            生成物/manifest 契约
  error/              错误码与恢复语义
  media/              App 媒体呈现策略
  observability/      埋点与语义扫描
  page/               页面矩阵、modal 与设置壳
  platform/           平台能力隔离与启动矩阵
device/               本地设备启动、停止和首帧诊断
env/                  App 四环境配置与包纯度门
fonts/                App 字体资源校验
gamma/                gamma-local App 侧验证入口
ios/                  iOS 本地构建后端
web/                  Web 离线资源校验
tools/
  design_system/      设计系统人工检查工具
  device/             设备发现与实例枚举工具
  gamma/              gamma-local 专项人工验证工具
  ios/                iOS 清理与日志辅助工具
  media/              媒体资源生成工具
cli.py                App 薄 CLI 入口
```

领域 L1 目录必须与 `lib/service/<service_name>` 同名；只有真实存在 App 自治脚本的
L1 才建立目录，不为其余服务创建占位树。跨服务/壳层门落 `runtime/<concern>/`；
人工工具落 `tools/<concern>/`，并由本 README、CLI、Make、runbook、spec 或测试中的
至少一处当前引用证明 owner 与用途，不得冒充对象门。

禁止在本目录恢复 Figma 同步工具链、个人助手脚本或第二套环境编排入口。
禁止恢复旧顶层 `auth/`、`content/`、`chat/`、`media/`、`settings/`，以及 `runtime/` 根平铺 verifier。
根目录只允许 `cli.py`、`_common/` 与本 README；缓存、编辑器备份和临时脚本一律写到
`.qwq_output` 或仓外受管缓存。

人工设备诊断入口：

- `quwoquan_app/scripts/tools/design_system/scan_material_leaks.py`：人工扫描
  Cupertino surface 的 Material 泄漏。
- `quwoquan_app/scripts/tools/device/inspect_ios_native_startup.py`：对已构建的 `Runner.app` 执行受控
  Simulator 启动故障检查。
- `quwoquan_app/scripts/tools/device/discover_flutter_mobile_devices.py`：供 Ops Patrol 读取当前 Flutter
  移动设备，不承担环境编排。
- `quwoquan_app/scripts/tools/gamma/intersection_remote_smoke.py`：签发受控会话并
  运行 intersection Remote smoke。
- `quwoquan_app/scripts/tools/ios/ios_shortcut_log_hygiene.py`：审计并过滤本地 iOS Shortcuts 索引噪声。
- `quwoquan_app/scripts/tools/media/generate_native_launch_assets.py`：从 Flutter
  最终帧导出生成原生启动资源。
