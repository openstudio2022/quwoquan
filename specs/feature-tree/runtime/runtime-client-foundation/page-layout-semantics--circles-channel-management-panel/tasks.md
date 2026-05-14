# L4 任务：circles-channel-management-panel

## 当前交付任务

- [x] M1（metadata）确认本特性为端侧页面语义改造，不新增/变更 `contracts/metadata/*`
- [x] C1（codegen）执行 `make -C quwoquan_service verify-metadata && make -C quwoquan_service codegen-content-service && make -C quwoquan_service codegen-app`，确保基线无回归
- [x] B1（业务）`CirclesPage` 顶部右侧入口替换为三横频道管理图标
- [x] B2（业务）在一级 tab 下方实现可展开/收起的频道管理面板（微博式布局，覆盖内容区）
- [x] B2.1（业务）保持圈子一级 tab 左右边距与内容区语义一致（含右侧管理图标对齐）
- [ ] B2.2（业务）面板接入后验证 tab 滚动稳定性：恢复“推荐显示 + 选中居中 + 过中线锚定”全路径无跳变（存量）
- [x] B3（业务）实现「我的频道/全部频道」增删流转：`x` 下沉未选、`+` 上浮已选末尾
- [x] B4（业务）实现「我的频道」拖拽排序，一级 tab 顺序同步更新
- [x] B5（业务）实现首装默认规则：`car`、`humanity`、`sports` 在未选；关注与推荐固定不参与管理
- [x] B6（业务）本地持久化频道偏好（顺序 + 选中状态）并在启动恢复
- [x] B7（业务）动作色统一蓝色主色，避免橘色
- [ ] T1（测试）补充/更新圈子页频道管理交互测试（搁置，手动验证通过）
- [ ] T1.1（测试）补充 tab 稳定性回归（存量，待恢复锚定状态机后补齐）
- [x] T2（测试）执行 `flutter analyze quwoquan_app/lib/` 与 `python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py`

## 规划任务

- [ ] P1 评估是否抽离 `ChannelManagementPanel` 为可复用组件（发现/圈子共享）

## 存量问题（deferred）

- [ ] L1 恢复圈子一级 Tab 关键交互：推荐可见、选中居中、跨过中线触发锚定（关注被挤出、推荐置顶），并保持滚动/展开收起全路径无跳变
