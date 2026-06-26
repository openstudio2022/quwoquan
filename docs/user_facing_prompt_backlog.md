# 用户可见提示语治理清单

> 与 `docs/outstanding_risks_backlog.md` 并列维护。本清单登记空态、失败态、降级态、权限态、加载长等待、弱网/重试和不可用占位等用户可见提示语，记录出现原因和优化状态；不替代 `UITextConstants`、l10n 或 metadata errors 真相源。

## 使用规则

- 每条提示语使用 `- [ ]` / `- [x]` 复选框维护。
- `风险等级` 使用 `P0` / `P1` / `P2` / `P3`：
  - `P0`: 误导、合规、隐私或安全风险。
  - `P1`: 阻断转化、造成错误行动引导或明显旅程断点。
  - `P2`: 低质、含混、语气不稳或价值表达不足。
  - `P3`: 可优化但不影响理解。
- `状态` 必须明确写为 `待审视`、`进行中` 或 `已解决（日期 + 证据）`。
- 新增条目必须补齐场景、触发原因、当前提示语、问题类型和涉及文件。
- 关闭条目时必须补验证证据，例如 widget 测试、截图、UAT 回放、门禁或文案评审记录。

## 模板

- [ ] PROMPT-XXX 标题
  - 区域: App / Service / Data / Ops / Portal
  - 域: `<domain>`
  - surface/组件: `<surface or widget>`
  - 场景: ...
  - 触发原因: ...
  - 当前提示语: ...
  - 问题类型: 空态 / 失败态 / 降级态 / 权限态 / 加载长等待 / 弱网重试 / 不可用占位 / 其他
  - 建议方向: ...
  - 风险等级: P0 / P1 / P2 / P3
  - 涉及文件: `path/to/file`
  - 状态: 待审视
  - 验证证据: 待补

## 主页与交集（Profile / Intersection）

- [x] PROMPT-001 他人主页无交集空态暗示浏览即可产生真实交集
  - 区域: App
  - 域: `object-homepage-network / user-profile`
  - surface/组件: `OtherProfileIntersectionCard`
  - 场景: 他人主页「我与TA的交集」无有效共同线索时展示空态。
  - 触发原因: 交集服务返回空、不可解析 viewer/object query，或有效 `primaryText` 为空。
  - 当前提示语: `现在还没有足够清晰的共同线索。共同关注、互动或加入同一圈子后，这里会呈现你们真正相关的连接。`
  - 问题类型: 空态
  - 建议方向: 避免承诺单纯浏览会生成交集，强调真实共同线索与可沉淀连接的动作来源。
  - 风险等级: P2
  - 涉及文件: `quwoquan_app/lib/core/constants/ui_text_constants_values.dart`, `quwoquan_app/lib/ui/user/widgets/other_profile_intersection_card.dart`
  - 状态: 已解决（2026-06-26；文案替换为连接导向空态）
  - 验证证据: `quwoquan_app/test/ui/user/widgets/profile_shell_widget_test.dart`

- [x] PROMPT-002 他人主页无交集仍展示查看全部假入口
  - 区域: App
  - 域: `object-homepage-network / user-profile`
  - surface/组件: `OtherProfileIntersectionCard`
  - 场景: 他人主页「我与TA的交集」为空、失败或不可解析时，底部仍出现 `查看全部`。
  - 触发原因: `ProfileInsightSectionCard` 原先强制渲染 footer action，调用方无论是否有可展示交集都传入入口。
  - 当前提示语: `查看全部`
  - 问题类型: 空态
  - 建议方向: 仅在存在可展示交集时提供列表入口；空态保留说明，不提供无价值点击。
  - 风险等级: P1
  - 涉及文件: `quwoquan_app/lib/ui/user/widgets/profile_intersection_insight_primitives.dart`, `quwoquan_app/lib/ui/user/widgets/other_profile_intersection_card.dart`
  - 状态: 已解决（2026-06-26；footer action 改为可选，OtherProfileIntersectionCard 仅非空态展示入口）
  - 验证证据: `quwoquan_app/test/ui/user/widgets/profile_shell_widget_test.dart`
