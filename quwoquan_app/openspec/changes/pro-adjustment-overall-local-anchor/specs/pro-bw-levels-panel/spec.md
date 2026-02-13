## ADDED Requirements

### Requirement: 黑白色阶双轴调节面板

专业修图 SHALL 提供“黑白色阶”独立工具面板，采用两条调节线布局：白色色阶与黑色色阶。两条调节线范围 MUST 为 `-100..100`，默认值 MUST 为 `0`，并支持连续精细滑动。

#### Scenario: 首次进入黑白色阶

- **WHEN** 用户从专业工具箱进入“黑白色阶”
- **THEN** 面板显示“白色色阶/黑色色阶”两条调节线，且两者默认值均为 `0`

#### Scenario: 参数联动

- **WHEN** 用户拖动任一色阶调节线
- **THEN** 对应参数数值与滑条位置同步更新，另一条参数保持不变

### Requirement: 专业级 Levels 映射语义

黑白色阶调整 MUST 采用输入黑白点重映射语义（Levels），而非简单亮度叠加。系统 SHALL 保证黑点与白点存在最小安全间隔，避免反转或断层。

#### Scenario: 调整黑色色阶

- **WHEN** 用户提高黑色色阶
- **THEN** 暗部输入阈值上移，画面黑位收紧且过渡连续

#### Scenario: 调整白色色阶

- **WHEN** 用户提高白色色阶
- **THEN** 亮部输入阈值下移，画面高位增强且无明显断层

### Requirement: 会话对比与提交语义

黑白色阶工具会话 SHALL 支持 compare 图标。compare 基线 MUST 为进入当前黑白色阶会话时的图像状态。`X` 与 `✓` 的提交/回滚语义 MUST 与其它专业工具一致。

#### Scenario: Compare 基线

- **WHEN** 用户按住或切换 compare
- **THEN** 图片切换为进入黑白色阶会话时的基线图像，释放或关闭后恢复当前调节结果

#### Scenario: 会话提交

- **WHEN** 用户点击 `✓`
- **THEN** 黑白色阶作为 `proTools` 的独立步骤提交到历史（`bwLevelsAdjustments`）
