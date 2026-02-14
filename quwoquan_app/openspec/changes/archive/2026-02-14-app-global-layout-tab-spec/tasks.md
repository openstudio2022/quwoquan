## 1. 规格归档

- [ ] 1.1 执行 `npx openspec archive --change app-global-layout-tab-spec` 将 delta 合并进 openspec/specs/app-global/spec.md
- [ ] 1.2 检查合并后的 app-global spec 包含「布局与整体交互体验要求」「一级 Tab 转场与交互」两大章节

## 2. 实现核对

- [ ] 2.1 核对 CenteredScrollableTabBar 满足规格：可见数 3/5/7/9/11、左右渐变、点击居中、anchorTabId、滑动吸附
- [ ] 2.2 核对 discovery_page、circles_page 一级 Tab 同语义（选中态、字号、热区、动画）
- [ ] 2.3 核对视频全屏沉浸时 bottomNavHiddenProvider 控制底部导航隐藏，退出沉浸或滑动切换 Tab 时恢复
- [ ] 2.4 运行 flutter analyze 与语义审计脚本，确认无硬编码与违规
