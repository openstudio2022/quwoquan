# P4 图库真实接入合规：图虫/Pinterest 受限如实标注 + 授权完整性硬门 + 非中文译简体门

规划真相源：`/Users/zhaoyuxi/.cursor/plans/提示词重构与三类解耦放量_2f1c2e11.plan.md`（P4）。

## 目标（P4 判据）

- 图虫/Pinterest 真实抓取适配器，优先官方 API / 合规路径。
- 非中文统一译简体中文。
- 授权完整性硬门：页 / 集合级授权传播到每张图（license/credit/termsUrl/authorizationProof/usageScope），无授权不进发布面。
- robots/ToS/登录墙阻断**如实标注受限 + 替代路径**，不假装绕过、不无视版权。

## 诚实结论（关键）

图虫（图虫创意，多为 VCG 商业授权）与 Pinterest（视觉发现平台）绝大多数图片受版权保护，平台
ToS / robots / 登录墙**禁止抓取他人图片后再发布**。Pinterest 官方 API（v5）面向管理自有 pin/board，
不提供他人图片检索后转载的授权；图虫图片需逐图取得创作者/平台授权。

因此**唯一诚实的"真实适配器"是合规探针**：以 registry rightsPolicy 为唯一真相源把来源分级，对受限
来源**如实标注受限**（`bypassAttempted=false`）并给出**替代路径**（回到 Wikimedia Commons / Openverse
等开放许可图池经官方 API 真实抓取可发布图），绝不写绕过 ToS / 登录墙的抓取器。写一个"绕过版"抓取器
将直接违反规划"不假装绕过、不无视版权"，故不实现。

## 本批改动（metadata-first / 单一真相源）

### P4a 图库合规分级 + 受限如实标注（新增模块）

- `quwoquan_data/scripts/download/research/image_provider_compliance.py`（新增）
  - 单一真相源 = `content_source_registry.yaml` 的 `common.image` / `verticals.*.image` 行 `rightsPolicy`/`fetchMode`/`defaultRole`；
    禁止在判定/抓取代码另维护第二套"哪些图库可发布"映射。
  - `rightsPolicy → accessMode`：
    - `open_license_required` → `open_license_publishable`（Commons/Openverse，直接可发布）
    - `asset_level_required` → `asset_level_conditional`（Unsplash/Pexels/Flickr，逐资产授权后可发布）
    - `creator_authorization_required` → `restricted_creator_authorization`（图虫/500px/Behance，逐图创作者授权）
    - `commercial_license_required` → `restricted_commercial_license`（Getty/Shutterstock/VCG，购买授权）
    - `reference_only` → `restricted_reference_only`（Pinterest，仅参考，永不直接发布）
  - `image_provider_restriction()`：受限来源的如实受限记录（受限原因 + `bypassAttempted=false` + `requiresProof` 逐图授权凭证 + `alternativePath` 开放许可图池）。
  - `professional_library_compliance_summary()`：图库合规审计摘要，写入 research report 使"受限+替代路径"决策可审计。
- `quwoquan_data/scripts/download/research/auto_plan_writer.py`
  - image lane 选中时把 `professionalImageLibraryCompliance` 摘要写入 research report（真实消费，非死代码）：图虫/Pinterest/商业图库为何不直接进发布面、合规替代是什么，均可审计。

### P4b 授权完整性硬门（既有硬门复用 + 契约固化）

- 既有硬门已在 `download/research/source_quality.py`（`_candidate_gate` / `_collection_gate` / `_collection_publishable_image_urls`）与 `vertical/license.py`（`validate_image_rights`）落地：
  集合/页级授权传播到每张图，缺逐图 `url/sourceCollectionId/creator/collectionPageUrl/license/termsUrl/authorizationProof` 或非自由许可（NC/ND）一律阻断。
- 本批新增契约测试固化该硬门对图虫集合的行为（全授权通过 / 缺 authorizationProof 阻断 / NC 许可阻断），防回退。

### P4c 非中文图片元数据译简体门（既有门复用 + 契约固化）

- 既有 `_common/localization.py`（`simplified_chinese_publish_issues`）与 `_common/asset_placement.py`（`_caption_is_degraded` / `caption_semantic_issues`）已是简体中文发布门唯一真相源：英文/拉丁主导或繁体未折叠的标题/正文/caption 阻断发布（翻译语义由 Agent 阶段完成，原文由 source unit 存档）。
- 本批新增契约测试固化"英文 caption / 英文标题阻断、简体合格放行"，防第二真相源漂移。

## 测试与门禁

- 新增 `quwoquan_data/tests/local_contract/common/test_image_provider_compliance__local_contract_test.py`（8 用例）：
  - P4a 图虫=逐图创作者授权 / Pinterest=仅参考，均 restricted + `bypassAttempted=false` + 替代路径；Commons/Openverse 可发布无受限记录；合规摘要可审计且诚实。
  - P4b 全授权通过硬门 / 缺 authorizationProof 阻断 / NC 许可阻断。
  - P4c 英文 caption 退化阻断 + 中文合格；英文标题阻断 + 简体合格。
- 已接入 `quwoquan_data/scripts/verify/verify_quwoquan_data.sh`（紧随 P3 三类解耦用例）。
- `verify_content_source_registry()` 无 issue（registry 未改，分级以既有 rightsPolicy 为真相源）。

## 验证证据

```
$ quwoquan_data/.venv/bin/python quwoquan_data/tests/local_contract/common/test_image_provider_compliance__local_contract_test.py
PASS test_p4a_compliance_summary_is_auditable_and_honest
PASS test_p4a_open_license_providers_publishable
PASS test_p4a_tuchong_pinterest_restricted_with_alternative_path
PASS test_p4b_full_per_image_authorization_passes_gate
PASS test_p4b_missing_per_image_authorization_blocks_publish
PASS test_p4b_unsupported_license_blocks_publish
PASS test_p4c_non_chinese_image_caption_blocked
PASS test_p4c_non_chinese_title_blocked_for_publish
image provider compliance tests passed (8)
```

## 作用域

仅改 `quwoquan_data/**` 与 `artifacts/**`，未触碰 `quwoquan_app/**` 与他流 metadata/_shared 漂移。
