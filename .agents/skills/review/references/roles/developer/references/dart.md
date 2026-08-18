# Dart 编码标准

视觉与 token 归 ux（[flutter-design-system.md](../../ux/references/flutter-design-system.md)），
目录归属与依赖方向归 architect（[app-layering.md](../../architect/references/app-layering.md)），
返回值四态见 [result-state-semantics.md](result-state-semantics.md)。

## MUST NOT：相对路径 import

```dart
// ❌ 禁止
import '../../content_service/content/post/presentation/work_browser_entry_page.dart';
import '../widgets/media_post_card.dart';

// ✅ 必须
import 'package:quwoquan_app/service/content_service/content/post/presentation/work_browser_entry_page.dart';
import 'package:quwoquan_app/design_system/surfaces/conversation_sheet.dart';
```

## MUST NOT：产品名做标识符

路径、类名、判断条件都按**领域**命名，不按产品名。产品名会随品牌改名而全仓失效。

```dart
// ❌ 禁止
lib/service/assistant_service/.../xiaoqu_home_page.dart
if (msg['senderName'].toString().contains('小趣')) { }

// ✅ 必须
lib/service/assistant_service/.../assistant_home_page.dart
if (msg['senderId'] == AppConceptConstants.assistantSenderId) { }
```

## MUST：错误码经 codegen 枚举

错误码与用户可见文案由所属服务 `contracts/<context>/<object>/errors.yaml` 定义，
codegen 出 `*ErrorCode` 枚举。硬编码 code 字符串会在契约改名时静默失配。

```dart
// ❌ 禁止
switch (e.code) {
  case 'INTEGRATION.USER.location_unavailable':
    return '暂时无法获取当前位置';
}
expect(actual.code, 'INTEGRATION.MIDDLEWARE.upstream_timeout');

// ✅ UI 展示
IntegrationLocationErrorCode.fromCode(e.code).toDisplayMessage(context.l10n)

// ✅ 测试断言
expect(actual.code, IntegrationLocationErrorCode.upstreamTimeout.code)
```

## MUST NOT：按 DTO 子类型分支

对抽象基类与共享接口（如 `PostBaseDto`）的消费，禁止在业务或 UI 代码里用
`is` / `is!` / `as` / `whereType<T>()` 分支具体子类型。差异收口到基类接口、抽象 getter
或语义化 capability。

```dart
// ❌ 禁止
if (post is VideoPostDto) return post.thumbnailUrl;
final photos = items.whereType<PhotoPostDto>().toList();
final article = post as ArticlePostDto;

// ✅ 必须
if (post.isVideoLike) return post.primaryVisualUrl;
final visuals = items.where((item) => item.displayFormat == 'image').toList();
```

新增字段访问需求时**先补基类契约再改消费方**。唯一例外是反序列化与工厂分发层
（如 `postBaseDtoFromMap()`）可按 wire format 决定实例化哪个子类；测试可断言具体类型，
生产代码不行。

## MUST NOT：在业务逻辑里写契约字段名字符串

生成的契约类（例如 `assistant_turn.g.dart` 的 `AssistantTurnOutput`，
由 `tools/codegen_app_metadata` 从 `schema.yaml` 生成）已提供类型化访问。

```dart
// ❌ 禁止
final userMd = (parsed['userMarkdown'] as String?)?.trim() ?? '';
final decision = (parsed['decision'] as Map?)?.cast<String, dynamic>() ?? {};

// ✅ 必须
final turn = AssistantTurnOutput.tryParse(parsed);
final userMd = turn?.userMarkdown ?? '';
```

字段名字符串只允许出现在生成的 `fromJson()` / `tryParse()` 内部。
**改字段先改 `schema.yaml` 再 codegen**，不要手改 `.g.dart`，也不要在消费侧加 map key 访问。

## 状态管理（Riverpod）

- [MUST] State 类不可变：`const` 构造 + `copyWith` + `operator ==` / `hashCode`。
- [MUST] StateNotifier 的异步操作都有错误处理，并防重复加载（`if (state.isLoading) return`）。
- `ref.watch` 只在 build 中监听；`ref.read` 执行动作；`ref.listen` 处理副作用；
  `ref.watch(provider.select(...))` 做性能优化。
- 异常层次：`AppException`（abstract）派生 `NetworkException` / `ValidationException` /
  `AuthenticationException` / `BusinessException` / `NotFoundException`。

## 提交前

```bash
cd quwoquan_app && flutter analyze
python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py
python3 quwoquan_app/scripts/runtime/page/verify_settings_canonical.py
```
