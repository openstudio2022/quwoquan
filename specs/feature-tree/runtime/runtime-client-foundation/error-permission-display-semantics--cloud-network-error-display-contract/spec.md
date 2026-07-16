# L4 契约：cloud-network-error-display-contract

## 功能说明

云端/网络错误的统一展示契约：展示方式选择（页态 / 区块态 / 动作反馈）、语义 token、l10n key 约定，以及列表首屏/缓存回退/分页追加三类错误的差异化语义。

## 范围

- 阻塞性错误（页面/列表首次加载失败）→ 页态/区块态卡片
- 次要错误（提交失败、单次操作失败）→ `AppActionErrorFeedback`
- 表单提交、限流、网络或第三方依赖失败 → 操作点附近的 `AppFormErrorCard`
- 字段格式、验证码不匹配等输入错误 → `AppInlineFieldError`
- 列表首屏失败 / 缓存回退失败 / 分页追加失败三类语义必须区分
- Token：colorScheme.error、bodyMedium、AppSpacing.interGroup*
- l10n：loadFailed、submitFailed、networkUnavailable；domain 专属见 errors.yaml

## 与父节点关系

父节点：`error-permission-display-semantics` L3

## 验收标准

- 创作页提交失败使用动作级反馈或页内错误区，而非吞错后固定字符串
- 附近位置/发现流首屏加载失败使用内联页态/区块态
- 发现流分页追加失败保留旧内容并在尾部展示重试，不清空现有列表
- 所有错误文案来自 l10n，颜色/字号使用设计系统
- 表单错误卡提供标题、正文和可选恢复动作，使用 `Semantics(liveRegion: true)`，编辑、重试或成功后清除且不抢走输入焦点
- **local_contract contract 错误码→UiErrorSemantic 映射契约**：CloudException.code / RuntimeFailure → 正确 message / action / scope
- **L1b 位置选择页错误态**：注入 FakeLocationService 抛 CloudException 时，UI 展示正确内联错误
- **L1c 创作流**：选位置 → 云端超时 → 内联错误（非 SnackBar）
- **依赖**：L1b 错误态需 permission-card 的 LocationPermissionChecker（FakeChecker 返回 granted 以进入 nearby()）
