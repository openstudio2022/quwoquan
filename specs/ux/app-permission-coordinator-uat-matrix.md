# AppPermissionCoordinator 真机 UAT 矩阵

> **验收意图**：`user_acceptance`
> **特性树**：`runtime-client-foundation` / `error-permission-display-semantics`
> **真相源**：`AppPermissionCoordinator`、`specs/ux/error-and-permission-semantics.md` §2.8–§2.11

在 **iOS** 与 **Android** 各执行一遍下表。JIT 聊天场景建议全新安装或清除 App 数据。

## 前置

- iOS：确认 Podfile `PERMISSION_*` 宏已启用并 `pod install`。
- 记录设备型号、OS 版本、构建 flavor。

## 场景矩阵

| # | 场景 | 操作步骤 | iOS 期望 | Android 期望 | iOS ✓ | Android ✓ |
|---|------|----------|----------|--------------|-------|-----------|
| 1 | JIT 首次按住说话 | 卸载重装 → 聊天按住说话 | **仅 L1 系统弹窗**，无 App primer | 同左 | | |
| 2 | 系统弹窗允许 | 弹窗点「允许」 | 直接录音，零跳转 | 同左 | | |
| 3 | 系统弹窗拒绝 | 弹窗点「不允许」 | **一次** L3 gate（标题含「需要在设置中开启」） | 同左（Android 可能可多次 request 后再 permanent） | | |
| 4 | 去设置未开启返回 | L3 点「去设置」→ 未改权限 → 返回 | **一次**失败 Toast；再按 **不弹**含去设置的 modal | 同左 | | |
| 5 | 设置中开启后返回 | L3 去设置 → 开启 → 返回 | 成功 Toast，可录音 | 同左 | | |
| 6 | 永久拒绝 + suppress | 永久拒绝后连续 5 次按住说话 | 仅 Toast，**无 modal 堆叠** | 同左 | | |
| 7 | 定位页 loop B | 创作选位置 → 去设置 → 未开返回 | 不自动再跳设置；可隐藏位置退出 | 同左 | | |
| 8 | 相册拒绝 | 创作选图 → 拒绝 | gate 有重试+去设置；suppress 后仅 Toast | 同左 | | |
| 9 | 语音上传失败 | 麦克风已授权，模拟上传失败 | **仅** status bar（`chatVoicePendingRetry`），无居中 dialog | 同左 | | |
| 10 | status bar 重试 | #9 后点「重试」 | 触发 offline queue，不弹权限框 | 同左 | | |
| 11 | Page L2 文案 | 相册/定位首次进入 | 「继续」与正文一致，含「系统弹窗」说明 | 同左 | | |

## 失败判定

- 一次按住说话出现 **2+ App modal**（不含系统弹窗）
- 语音失败 **modal + status bar** 同时存在
- primer 正文含「请点允许」但主按钮为「继续」且无「系统弹窗」说明
- 设置返回无任何反馈（成功或失败 Toast 均应出现一次）

## 证据

- 录屏或截图 + 勾选上表
- `flutter test test/local_contract/core/services/app_permission_coordinator__local_contract_test.dart`
