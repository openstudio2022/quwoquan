# Tasks: group-settings — 群设置页边界与对象级治理

## Phase A — 结构与边界冻结

- [ ] A1: 冻结群设置页区块：成员、资料、配置、个性化、退出群聊
- [ ] A2: 明确群设置页不承载 `举报群` 与 `拉黑群聊`
- [ ] A3: 明确群聊通话入口不在 AppBar/设置页，而在输入区 `+` 面板

## Phase B — 前端重构

- [ ] B1: 精简 `ChatSettingsPage` 的动作集合
- [ ] B2: 成员区保留查看与添加入口，不直接放举报/拉黑
- [ ] B3: 危险操作区仅保留 `退出群聊`
- [ ] B4: 将对象级治理入口迁移到成员卡片/成员主页/消息长按菜单

## Phase C — 与群聊通话联动

- [ ] C1: 群聊输入区 `+` 面板新增 `发起语音通话 / 发起视频通话`
- [ ] C2: 选人页接入 `<=8 默认全选，>8 默认不选`
- [ ] C3: 群设置页中移除通话相关入口

## Phase D — 测试

- [ ] D1: T2 — 群设置页 UI 边界回归
- [ ] D2: T2 — 对象级治理入口位置回归
- [ ] D3: T3 — 群聊通话入口路径回归
- [ ] D4: `make gate`

## Phase E — 全屏表单态基线（CR-20260329-002）

- [x] E1: `GroupManagePage` 对齐 `SettingsInsetFormPageScaffold` 与 `SettingsInsetGroupedSection`
- [x] E2: 解散/Toast 等文案迁入 `UITextConstants` 或 l10n（满足门禁）
- [x] E3: 验收 A9–A13（acceptance.yaml）
- [x] E4: `flutter analyze` + `verify_dart_semantic.py`
