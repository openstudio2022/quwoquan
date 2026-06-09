# 搜索商用化运行手册

## 观测事件

- `search.query.submitted`：query、mode、objectTypes、sourceSurfaceId、guest/auth、voiceInput。
- `search.suggest.exposed`：suggest count、provider、latencyMs。
- `search.result.clicked`：objectType、objectId、rank、matchedField、referralSource。
- `search.degrade`：code、objectType、provider、fallbackApplied。
- `search.zero_result`：query、objectTypes、queryVariants、tagEntityExpanded。
- `assistant.search.citation_opened`：citationId、objectType、sourceDomain、rank。
- `public_web.seo.rendered`：objectType、visibility、indexable、schemaType。
- `public_web.transfer.resolved`：uaBucket、launchMethod、fallbackURL、targetEntity。

## SLO

- 首结果延迟 P95：`result <= 900ms`，`suggest <= 250ms`。
- 搜索成功率：`>= 99.0%`，provider 单点失败必须转为 degrade signal。
- degrade rate：`<= 5%`；`circle_group_remote_empty` 单独按 fallback 告警。
- zero-result rate：`<= 12%`，高频 query 进入 tag/entity expansion 词表修复。
- Xiaoqu citation rate：`>= 80%` 的小趣检索回答至少包含 2 条 typed citation。
- SEO 抓取错误率：`<= 1%`；sitemap URL 404/5xx 任意超过阈值触发回滚。

## 回滚开关

- `search.core.enabled`：关闭后 App façade 回退旧 repository 聚合。
- `search.tag_entity_boost.enabled`：关闭 tag/entity expansion 与 ranking boost。
- `assistant.canonical_search.enabled`：关闭后小趣展示结构化 unavailable，不回退 fake citation。
- `public_web.seo.enabled`：关闭公开 HTML 服务，仅保留 noindex fallback。
- `public_web.transfer.enabled`：关闭 UA 分流，统一跳下载/预览 fallback。

## 权限与降级

- guest 可检索 public content、entity、circle 与 web.document；私有 chat.message/user.profile 扩展必须要求授权上下文。
- `web.document` provider 不可用时，站内 provider 继续返回结果，并展示 `web_document_unavailable` degrade。
- private / 审核未过对象不进 sitemap，HTML 响应必须 `noindex,nofollow`。
