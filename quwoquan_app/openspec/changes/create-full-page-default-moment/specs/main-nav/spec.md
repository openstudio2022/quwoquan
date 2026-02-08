# main-nav

## MODIFIED Requirements

### Requirement: 创作入口打开创作全页

「创作」入口须打开创作全页（如导航至 `/create`），而不是打开创作入口抽屉。点击创作后 SHALL 进入全屏创作页，默认为发微趣 Tab；底部导航当前选中项的处理与产品约定一致（可为切换至创作页或保持原选中项，以与全页路由一致为准）。

#### Scenario: 创作打开全页

- **WHEN** 用户点击「创作」入口
- **THEN** 应用导航至创作全页（如 `/create`），展示创作页且默认发微趣，不展示入口抽屉

#### Scenario: 创作入口不打开抽屉

- **WHEN** 用户点击「创作」入口
- **THEN** 不展示创作入口抽屉（CreateEntrySheet）；创作流程以全页为首屏
