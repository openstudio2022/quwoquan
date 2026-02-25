# L4 任务：arb-gen-l10n-string-extraction

## 当前交付任务

顺序：基础设施 → 字符串迁移 → 扩展访问器 → 参数化 → 逐文件清理

- [x] **T1：ARB 基础设施搭建**
  - 创建 `quwoquan_app/l10n.yaml`（`arb-dir: lib/l10n`，`template-arb-file: app_zh.arb`）
  - 创建 `quwoquan_app/lib/l10n/` 目录
  - 在 `pubspec.yaml` 中确认 `generate: true` 与 `flutter_localizations` SDK dep
  - 在 `lib/main.dart` 的 `localizationsDelegates` 中添加 `AppLocalizations.delegate`
  - 执行 G2：`flutter analyze`
  
- [x] **T2：字符串常量迁移至 ARB**
  - 将 `UITextConstants`（520 行）所有 `static const String xxx = 'yyy'` 迁移为 `app_zh.arb` 的 `"xxx": "yyy"` 条目
  - 将 `AppStrings`（63 行）同理迁移（注意与 UITextConstants 重叠 key 去重）
  - 创建 `app_en.arb`，key 集合与 `app_zh.arb` 完全一致，值全部为 `"TODO: translate"`
  - 执行 `flutter gen-l10n`，确认生成无报错
  - 执行 G2：`flutter analyze`

- [x] **T3：BuildContext 扩展访问器**
  - 创建 `lib/l10n/l10n.dart`：`extension AppLocalizationsX on BuildContext { AppLocalizations get l10n => AppLocalizations.of(this); }` + `export 'app_localizations.dart'`
  - 执行 G2：`flutter analyze`

- [x] **T4：参数化 ARB 条目**
  - 在 `app_zh.arb` 添加 `allCommentsCount`（`int count`）
  - 在 `app_zh.arb` 添加 `hoursAgoTemplate`（`int delta`）
  - 在 `app_en.arb` 同步添加对应占位条目
  - 重新执行 `flutter gen-l10n`，确认生成无报错
  - 执行 G2：`flutter analyze`

- [x] **T5：discovery_page.dart 清理**
  - 替换 `'刚刚'` → `context.l10n.justNow`
  - 替换 `'${delta}小时前'` → `context.l10n.hoursAgoTemplate(delta)`
  - 执行 G2：`flutter analyze`

- [x] **T6：article_detail_page.dart 清理**（16 处）
  - `'文章'` → `context.l10n.discoveryTabArticle`
  - `'未找到该文章'` → 新增 key `articleNotFound`
  - `'匿名'` → 新增 key `anonymous`
  - `'官方账号'` → 新增 key `officialAccount`
  - `'资深创作者'` → 新增 key `seniorCreator`
  - `'关注'` → `context.l10n.follow`
  - `'已关注'` → `context.l10n.following`
  - `'著作权归作者所有'` → 新增 key `copyrightNotice`
  - `'商业转载请联系作者获得授权'` → 新增 key `commercialReproductionNotice`
  - `'全部评论 $_commentsCount'` → `context.l10n.allCommentsCount(_commentsCount)`
  - `'最热'` → 新增 key `sortByHot`
  - `'最新'` → 新增 key `sortByNew`
  - mock tag list `['生活方式', '深度好文', '推荐']` — 保留字面量（mock 数据）
  - `'用户${9527 + i}'` — 保留（mock 数据）
  - 所有新增 key 同步到 `app_zh.arb` + `app_en.arb`（TODO 占位）
  - 执行 G2：`flutter analyze`

- [x] **T7：author_profile_page.dart 清理**（40+ 处）
  - 错误/加载：`'加载中...'` → `context.l10n.loading`；`'加载失败'` → `context.l10n.loadFailed`；`'未知错误'` → 新增 `unknownError`；`'重试'` → `context.l10n.retry`
  - Tab：`'全部'` → `context.l10n.circleSubAll`；`'图片'` → `context.l10n.circleSubPhoto`；`'视频'` → `context.l10n.circleSubVideo`；`'文章'` → `context.l10n.discoveryTabArticle`
  - 统计：`'关注'` → `context.l10n.follow`；`'圈子'` → 新增 `circles`；`'粉丝'` → 新增 `fans`；`'获赞'` → `context.l10n.circleLikes`
  - 动作：`'已关注'` → `context.l10n.following`；`'私信'` → `context.l10n.message`；`'屏蔽用户'` → 新增 `blockUserAction`
  - 互动文本（条件字符串）：新增 `likedTheirPhoto`、`likedTheirArticle`、`theyLikedOthersArticle` 等独立 key
  - `'这个人很懒，什么都没有写'` → 新增 `emptyBio`；`'暂无互动内容'` → 新增 `noInteractionContent`；`'刚刚'` → `context.l10n.justNow`
  - `'交集详情'` → 新增 `resonanceDetail`；`'你们有'` → 新增 `youHave`
  - 所有新增 key 同步到 `app_zh.arb` + `app_en.arb`
  - 执行 G2：`flutter analyze`

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启 |
|---|---|---|
| `lib/features/` 硬编码中文清理 | 范围大，按域排期 | i18n 基础设施稳定后 |
| `lib/components/` 硬编码中文清理 | 共享组件影响广 | 同上 |
| `verify_dart_semantic.py` CJK 字面量扩展 | 需调整 CI 脚本 | G3 验证通过后追加 |

## 未来演进任务

- 英文翻译填充（`app_en.arb` TODO → 真实翻译）
- 非 widget 上下文 locale 感知（LocaleProvider + StateNotifier）
