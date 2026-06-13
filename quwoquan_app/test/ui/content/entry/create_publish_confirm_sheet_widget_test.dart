import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_article_summary_generate_response_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_publish_confirm_sheet.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';

class _SummaryRepository extends MockContentRepository {
  _SummaryRepository({this.summary = 'AI 生成摘要', this.shouldThrow = false});

  final String summary;
  final bool shouldThrow;

  @override
  Future<ContentArticleSummaryGenerateResponseDto> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    if (shouldThrow) {
      throw StateError('summary failed');
    }
    return ContentArticleSummaryGenerateResponseDto(summary: summary);
  }
}

class _TagRepository extends MockTagRepository {
  _TagRepository({this.returnEmpty = false});

  final bool returnEmpty;

  @override
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  }) async {
    if (returnEmpty) return const <TagSearchResult>[];
    return <TagSearchResult>[
      TagSearchResult(tagRef: 'Topic/旅行/城市漫步', label: '城市漫步', score: 1),
    ];
  }
}

class _HomepageRepository extends MockHomepageRepository {
  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = 20,
  }) async {
    return const <HomepageSummary>[
      HomepageSummary(
        id: 'homepage_sight_west_lake',
        homepageType: 'sight',
        canonicalEntityId: 'entity:sight:west_lake',
        title: '西湖景区',
        subtitle: '杭州',
        coverUrl: 'https://example.com/west-lake.jpg',
        status: 'published',
      ),
    ];
  }
}

class _AssistantRepository extends MockAssistantRepository {
  _AssistantRepository({
    this.available = true,
    this.shouldThrow = false,
    this.includeCanonicalEntityId = true,
  });

  final bool available;
  final bool shouldThrow;
  final bool includeCanonicalEntityId;

  @override
  Future<AssistantCreationSuggestResponse> suggestCreationAssistance({
    required AssistantCreationSuggestRequest request,
  }) async {
    if (shouldThrow) {
      throw StateError('suggest failed');
    }
    final suggestedHomepages = available
        ? <AssistantSuggestedHomepageView>[
            AssistantSuggestedHomepageView(
              id: 'homepage_sight_west_lake',
              type: 'sight',
              displayName: '西湖景区',
              canonicalEntityId: includeCanonicalEntityId
                  ? 'entity:sight:west_lake'
                  : null,
            ),
          ]
        : const <AssistantSuggestedHomepageView>[];
    return AssistantCreationSuggestResponse(
      suggestedTagRefs: available
          ? const <String>['Topic/旅行/城市漫步']
          : const <String>[],
      suggestedHomepages: suggestedHomepages,
      suggestedSummary: available ? '小趣建议摘要' : null,
      available: available,
      unavailableReason: available ? null : 'skill_not_enabled',
    );
  }
}

Widget _buildApp({
  required ContentRepository contentRepository,
  TagRepository? tagRepository,
  HomepageRepository? homepageRepository,
  AssistantRepository? assistantRepository,
  ValueChanged<PublishSettings>? onConfirm,
}) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (context, state) => _Host(onConfirm: onConfirm),
      ),
      GoRoute(
        path: AppRoutePaths.homepagePickerPathTemplate,
        builder: (context, state) {
          final extra = state.extra is HomepagePickerPageRouteExtra
              ? state.extra! as HomepagePickerPageRouteExtra
              : null;
          return HomepagePickerPage(
            initialQuery: state.uri.queryParameters['query'] ?? '',
            initialSelection: extra?.initialSelection,
          );
        },
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(contentRepository),
      tagRepositoryProvider.overrideWithValue(
        tagRepository ?? _TagRepository(),
      ),
      homepageRepositoryProvider.overrideWithValue(
        homepageRepository ?? _HomepageRepository(),
      ),
      assistantRepositoryProvider.overrideWithValue(
        assistantRepository ?? _AssistantRepository(),
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp.router(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        routerConfig: router,
      ),
    ),
  );
}

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump();
  final button = tester.widget<CupertinoButton>(finder);
  button.onPressed?.call();
  await tester.pumpAndSettle();
}

class _Host extends StatelessWidget {
  const _Host({this.onConfirm});

  final ValueChanged<PublishSettings>? onConfirm;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      child: Center(
        child: CupertinoButton(
          child: const Text('打开发布确认'),
          onPressed: () async {
            final result = await Navigator.of(context).push<PublishSettings>(
              CupertinoPageRoute<PublishSettings>(
                builder: (_) => CreatePublishConfirmSheet(
                  initialSettings: const PublishSettings(),
                  contentIdentity: CreateContentIdentity.work,
                  title: '西湖一日游',
                  body: '这是一篇关于西湖城市漫步路线的正文，适合生成摘要。',
                  imageCount: 0,
                  hasVideo: false,
                  locationService: CreateLocationService(),
                  joinedCircles: const <CreateCircleOption>[],
                  recommendedCircles: const <CreateCircleOption>[],
                ),
              ),
            );
            if (result != null) {
              onConfirm?.call(result);
            }
          },
        ),
      ),
    );
  }
}

void main() {
  testWidgets('AI 摘要成功后写入摘要编辑框并可确认返回', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(summary: '西湖城市漫步摘要'),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createPublishGenerateSummaryButton));
    await tester.pumpAndSettle();

    expect(find.text('西湖城市漫步摘要'), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();
    expect(confirmed?.summary, '西湖城市漫步摘要');
  });

  testWidgets('AI 摘要失败不覆盖当前摘要', (tester) async {
    await tester.pumpWidget(
      _buildApp(contentRepository: _SummaryRepository(shouldThrow: true)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(TestKeys.createPublishSummaryField),
      '用户手写摘要',
    );

    await tester.tap(find.byKey(TestKeys.createPublishGenerateSummaryButton));
    await tester.pumpAndSettle();

    expect(find.text('用户手写摘要'), findsOneWidget);
    expect(find.text('摘要生成失败，已保留当前内容'), findsOneWidget);
  });

  testWidgets('标签和关联主页选择写入 PublishSettings', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishTagInput),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.enterText(find.byKey(TestKeys.createPublishTagInput), '城市');
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishAddTagButton),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(TestKeys.createPublishAddTagButton));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishEntityInput),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.enterText(find.byKey(TestKeys.createPublishEntityInput), '西湖');
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishAddEntityButton),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(TestKeys.createPublishAddEntityButton));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishConfirmButton),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed?.tagRefs, contains('Topic/旅行/城市漫步'));
  });

  testWidgets('裸标签输入无搜索结果时不写入 tagRefs', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(),
        tagRepository: _TagRepository(returnEmpty: true),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(TestKeys.createPublishTagInput));
    await tester.enterText(find.byKey(TestKeys.createPublishTagInput), '城市');
    await tester.ensureVisible(find.byKey(TestKeys.createPublishAddTagButton));
    await tester.tap(find.byKey(TestKeys.createPublishAddTagButton));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishConfirmButton),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed?.tagRefs, isEmpty);
  });

  testWidgets('小趣推荐写入标签、关联主页和摘要', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(),
        assistantRepository: _AssistantRepository(),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await _tapVisible(
      tester,
      find.byKey(TestKeys.createPublishAssistantSuggestButton),
    );
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.createPublishConfirmButton),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed?.tagRefs, contains('Topic/旅行/城市漫步'));
    expect(confirmed?.entityRefs, contains('entity:sight:west_lake'));
  });

  testWidgets('小趣推荐不可用时展示降级提示且不写入语义字段', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(),
        assistantRepository: _AssistantRepository(available: false),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await _tapVisible(
      tester,
      find.byKey(TestKeys.createPublishAssistantSuggestButton),
    );

    expect(
      find.byKey(TestKeys.createPublishAssistantSuggestError),
      findsOneWidget,
    );
    await tester.ensureVisible(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();
    expect(confirmed?.tagRefs, isEmpty);
    expect(confirmed?.entityRefs, isEmpty);
  });

  testWidgets('小趣推荐缺少 canonicalEntityId 时不写入 entityRefs', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        contentRepository: _SummaryRepository(),
        assistantRepository: _AssistantRepository(includeCanonicalEntityId: false),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await _tapVisible(
      tester,
      find.byKey(TestKeys.createPublishAssistantSuggestButton),
    );
    await tester.ensureVisible(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed?.tagRefs, contains('Topic/旅行/城市漫步'));
    expect(confirmed?.entityRefs, isEmpty);
  });
}
