import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';

import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import '../../../../../support/runtime/homepage_source_cards_boundary_overrides.dart';

import 'package:quwoquan_app/design_system/media/content_preview_card.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_text_constants.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart'
    show AppPageErrorState;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show
        ContentText,
        FoundationText,
        ObjectHomepageText,
        ProfileText,
        SearchText;
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider, intersectionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailEntityWishlistStateReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentRuntimeConfigProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart'
    show buildProductionContentRuntimeConfigDefaults;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider;
import 'package:quwoquan_app/runtime/errors/ui_error_appearance.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        EntityWishlistState,
        HomepageIntroduction,
        HomepageIntroductionSection,
        IntersectionReason,
        IntersectionTextSpan,
        ObjectPageBundle,
        ObjectPageContext,
        ObjectPageRolloutContext;

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';

List<Override> _homepageFacetOverrides(MockHomepageRepository repository) =>
    <Override>[
      ...homepageSourceCardsBoundaryOverrides(),
      homepageFacetSetProvider.overrideWithValue(repository),
    ];

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('主页详情页展示壳层摘要与 contextual publish 入口', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            const _StaticWishlistStateReader(),
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'viewer_demo',
              ownerUserId: 'viewer_owner_demo',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          // 「我的交集」卡需要当前用户（你×对象）；游客无「你」即收起（G2）。
          currentUserIdProvider.overrideWithValue('viewer_demo'),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: 'homepage_sight_west_lake'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('西湖景区'), findsWidgets);
    expect(
      find.text(ObjectHomepageText.objectMyIntersectionsTitle),
      findsOneWidget,
    );
    expect(find.text('推荐你了解西湖摄影'), findsOneWidget);
    expect(find.text(ObjectHomepageText.objectImpactTitleEntity), findsWidgets);
    expect(find.text('认领主页'), findsNothing);
    expect(find.text(ObjectHomepageText.homepageWishlistAction), findsWidgets);
    expect(
      find.text(ObjectHomepageText.entityActionPublishRecord),
      findsWidgets,
    );
    expect(find.text(ProfileText.profileDirectMessage), findsNothing);
    expect(find.byType(BottomNavigationWidget), findsNothing);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-compact-avatar')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-back-button')),
      findsNothing,
    );
    expect(find.text(ObjectHomepageText.objectTabRecord), findsWidgets);
    expect(find.text(ObjectHomepageText.objectTabDiscussion), findsWidgets);
    expect(
      find.text(ObjectHomepageText.objectTabRelatedCircles),
      findsOneWidget,
    );
    expect(find.text(ContentText.entityAboutTitle), findsNothing);
    expect(find.text('实体介绍'), findsNothing);
    expect(find.text('治理入口'), findsNothing);
    expect(find.text('统一对象键'), findsNothing);
    expect(find.text('对象页模板'), findsNothing);
    expect(find.text('灰度 cohort'), findsNothing);
    expect(find.text('主页管理'), findsNothing);

    // P3b 高保：记录 tab（默认激活=content）记录卡 footer 展示作者名 + 心形赞数，
    // 与圈子记录卡 footer 统一（作者名来自 HomepageContentPreview.authorName，
    // 赞数走 ContentCardMetric(likeCount)）。MasonryGridView 一次性 build，
    // 折叠区内允许 offstage；赞数数值由数据层 contract 断言保证（见末尾用例）。
    expect(find.text('湖畔慢行者', skipOffstage: false), findsWidgets);
    expect(find.byType(ContentCardMetric, skipOffstage: false), findsWidgets);

    await tester.tap(
      find.text(ObjectHomepageText.objectTabRelatedCircles).last,
    );
    await tester.pumpAndSettle();
    expect(find.text(HomepageDetailText.relatedGroupOpenAction), findsWidgets);

    await tester.tap(find.byKey(const ValueKey<String>('object-chrome-more')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('认领主页'), findsWidgets);
  });

  testWidgets('实体主页首屏卡片与内容区共用同一横向几何', (tester) async {
    tester.view.physicalSize = const Size(485, 1024);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'viewer_demo',
              ownerUserId: 'viewer_owner_demo',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          currentUserIdProvider.overrideWithValue('viewer_demo'),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'fixture_homepage_school_neworiental',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('homepage-background-media')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('homepage-identity-media')),
      findsOneWidget,
    );

    final identity = tester.getRect(
      find.byKey(const ValueKey<String>('homepage-summary-identity-card')),
    );
    final identityMedia = tester.getRect(
      find.byKey(const ValueKey<String>('homepage-identity-media')),
    );
    final intersection = tester.getRect(
      find.byKey(const ValueKey<String>('homepage-my-intersection-card')),
    );
    final impact = tester.getRect(
      find.byKey(const ValueKey<String>('homepage-impact-card')),
    );
    final tabSurface = tester.getRect(
      find.byKey(const ValueKey<String>('homepage-shell-tab-surface')),
    );
    for (final rect in <Rect>[intersection, impact, tabSurface]) {
      expect(rect.left, closeTo(identity.left, 0.5));
      expect(rect.right, closeTo(identity.right, 0.5));
    }
    expect(identity.left, closeTo(0, 0.5));
    expect(identity.right, closeTo(485, 0.5));
    expect(identityMedia.top, lessThan(identity.top));
    expect(identityMedia.bottom, greaterThan(identity.top));
  });

  testWidgets('实体主页头像划过工具栏后才显示吸顶小头像', (tester) async {
    tester.view.physicalSize = const Size(485, 1024);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
          currentUserIdProvider.overrideWithValue('viewer_demo'),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'fixture_homepage_school_neworiental',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final scrollable = find.byType(Scrollable).first;
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-compact-avatar')),
      findsNothing,
    );

    await tester.timedDrag(
      scrollable,
      const Offset(0, -120),
      const Duration(milliseconds: 500),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-compact-avatar')),
      findsNothing,
    );

    await tester.timedDrag(
      scrollable,
      const Offset(0, -340),
      const Duration(milliseconds: 500),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-compact-avatar')),
      findsOneWidget,
    );
  });

  testWidgets('选择模式显示 attach 按钮', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'homepage_sight_west_lake',
            selectionMode: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('关联到本次发布'), findsOneWidget);
  });

  testWidgets('alpha/mock 下支持 canonicalEntityId 直达实体主页', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: 'entity:sight:emeishan'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('峨眉山'), findsWidgets);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('我的交集中的新东方实体出点可直达实体主页', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'fixture_homepage_school_neworiental',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('新东方'), findsWidgets);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('canonical 新东方实体出点可直达实体主页', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: 'entity:school:neworiental'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('新东方'), findsWidgets);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('首页推荐取景地实体出点可直达实体主页', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'entity:photo_spot:hengshu_studio',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('横竖影像馆取景地'), findsWidgets);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('失效主页会展示明确提示并可安全返回首页', (tester) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(id: 'missing-homepage-id'),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (_, _) => const Scaffold(body: Center(child: Text('HOME'))),
        ),
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (context, state) =>
              HomepageDetailPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableMessage),
      findsOneWidget,
    );
    expect(find.text(SearchText.recoveryReturnAction), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('homepage-detail-error-back')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-detail-error-back')),
    );
    await tester.pumpAndSettle();

    expect(find.text('HOME'), findsOneWidget);
  });

  testWidgets('失效主页错误态跟随来源页面 appearance', (tester) async {
    Future<void> pumpFailure(UiErrorAppearanceMode mode) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authSessionControllerProvider.overrideWith(
              _GuestHomepageSession.new,
            ),
            behaviorRepositoryProvider.overrideWithValue(
              RecordingContentBehaviorRepository(),
            ),
            intersectionRepositoryProvider.overrideWithValue(
              _HomepageInMemoryIntersectionRepository(),
            ),
            contentRuntimeConfigProvider.overrideWithValue(
              buildProductionContentRuntimeConfigDefaults(),
            ),
            ..._homepageFacetOverrides(MockHomepageRepository()),
          ],
          child: MaterialApp(
            theme: ThemeData(
              brightness: mode == UiErrorAppearanceMode.light
                  ? Brightness.dark
                  : Brightness.light,
            ),
            home: HomepageDetailPage(
              homepageId: 'homepage_missing_for_source_appearance',
              sourceAppearanceMode: mode,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final errorState = tester.widget<AppPageErrorState>(
        find.byType(AppPageErrorState),
      );
      expect(errorState.semantic.appearanceMode, mode);
      await tester.pumpWidget(const SizedBox.shrink());
    }

    await pumpFailure(UiErrorAppearanceMode.light);
    await pumpFailure(UiErrorAppearanceMode.dark);
  });

  testWidgets('对象页 bundle 请求透传推荐与灰度上下文', (tester) async {
    final repository = _RecordingHomepageRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(repository),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            _RecordingHomepageIntroductionRepository(),
          ),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'hp-context',
            referralSource: ReferralSource.search,
            feedRequestId: 'feed-1',
            recommendationTraceId: 'trace-1',
            experimentBucket: 'A',
            rolloutCohort: 'city-hz',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(repository.lastReferralSource, 'search');
    expect(repository.lastFeedRequestId, 'feed-1');
    expect(repository.lastRecommendationTraceId, 'trace-1');
    expect(repository.lastExperimentBucket, 'A');
    expect(repository.lastRolloutCohort, 'city-hz');
    expect(find.text('认领主页'), findsNothing);
    expect(find.text(FoundationText.follow), findsOneWidget);
    expect(
      find.text(ObjectHomepageText.entityActionPublishRecord),
      findsOneWidget,
    );
  });

  // WP3 统一打标：实体主页消费 ObjectPageBundle.tagRefs（publish/tags 契约树
  // 全路径），展示叶子名胶囊；Format/** 内容载体标签滤除、全路径不外漏。
  testWidgets('实体主页展示 bundle tagRefs 叶子名标签并滤除 Format 载体标签', (tester) async {
    final repository = _TaggedHomepageRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(repository),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            _RecordingHomepageIntroductionRepository(),
          ),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: 'hp-tagged'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('homepage-tag-refs-wrap')),
      findsOneWidget,
    );
    expect(find.text('5A景区'), findsOneWidget);
    expect(find.text('都江堰市'), findsOneWidget);
    expect(find.text('观光游览'), findsOneWidget);
    // Format/** 是内容载体标签，对地点主页无展示价值。
    expect(find.text('攻略'), findsNothing);
    // 展示叶子名，契约全路径不得外漏。
    expect(find.textContaining('Entity/地点'), findsNothing);
    expect(find.textContaining('Topic/地理'), findsNothing);
  });

  testWidgets('bundle 无 tagRefs 且 detail 无 categoryTags 时不渲染标签行', (
    tester,
  ) async {
    final repository = _TaggedHomepageRepository(
      tagRefs: const <String>[],
      categoryTags: const <String>[],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(repository),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            _RecordingHomepageIntroductionRepository(),
          ),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: 'hp-untagged'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 不编造：数据工程/云侧都没打标时，不渲染标签行、不出占位胶囊。
    expect(
      find.byKey(const ValueKey<String>('homepage-tag-refs-wrap')),
      findsNothing,
    );
  });

  testWidgets('认识摘要卡使用 introduction summary 并跳转介绍页', (tester) async {
    final router = GoRouter(
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (context, state) =>
              HomepageDetailPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
        GoRoute(
          path: AppRoutePaths.homepageIntroductionPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (context, state) => Text(
            '介绍页:${state.pathParameters['id']}',
            textDirection: TextDirection.ltr,
          ),
        ),
      ],
      initialLocation: AppRoutePaths.homepageDetail(
        id: 'homepage_sight_west_lake',
      ),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _HomepageInMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          ..._homepageFacetOverrides(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            _RecordingHomepageIntroductionRepository(),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('真实 introduction summary'), findsOneWidget);
    final introCard = find.byKey(
      const ValueKey<String>('homepage-intro-slogan-card'),
    );
    await tester.ensureVisible(introCard);
    await tester.tap(introCard);
    await tester.pumpAndSettle();
    expect(find.text('介绍页:homepage_sight_west_lake'), findsOneWidget);
  });

  // P3b 数据契约：mock 对象页 bundle 的 highlightItems 必须透传记录卡 footer
  // 所需的 authorName / likeCount 由本用例的对象级最小输入显式给出。
  // 与 widget 测试一体：UI 断言作者名/赞数结构，此处锁定字段数值。
  test('mock 对象页 bundle highlightItems 透传记录卡 footer 作者名与赞数', () async {
    final repository = MockHomepageRepository();
    final bundle = await repository.getObjectPageBundle(
      'homepage_sight_west_lake',
    );
    expect(bundle.highlightItems, isNotEmpty);
    final first = bundle.highlightItems.first;
    expect(first.title, '西湖日落散步路线');
    expect(first.authorName, '湖畔慢行者');
    expect(first.likeCount, 328);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

final class _AuthenticatedHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() => AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: ['homepage', 'widget', 'access'].join('-'),
    refreshToken: ['homepage', 'widget', 'refresh'].join('-'),
    ownerId: 'viewer_owner_demo',
    activePersonaId: 'viewer_demo',
    accountState: 'active',
  );
}

final class _GuestHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}

class _HomepageInMemoryIntersectionRepository
    extends InMemoryIntersectionRepository {
  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 6,
  }) async {
    final reasons = await super.getObjectIntersections(
      objectId: 'fixture_homepage_travel_route_erhai',
      objectType: objectType,
      limit: 1,
    );
    if (reasons.isEmpty) {
      return reasons;
    }
    final wire = Map<String, Object?>.from(reasons.first.toWire())
      ..['objectKind'] = 'place'
      ..['relationObjectId'] = objectId
      ..['actionTargetId'] = objectId
      ..['primaryText'] = '推荐你了解西湖摄影'
      ..['primarySpans'] = <Map<String, Object?>>[
        const IntersectionTextSpan(text: '推荐你了解', role: 'plain').toWire(),
        const IntersectionTextSpan(text: '西湖摄影', role: 'plain').toWire(),
      ];
    return <IntersectionReason>[IntersectionReason.fromWire(wire)];
  }
}

class _RecordingHomepageRepository extends MockHomepageRepository {
  String? lastReferralSource;
  String? lastFeedRequestId;
  String? lastRecommendationTraceId;
  String? lastExperimentBucket;
  String? lastRolloutCohort;

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final now = DateTime.now().toUtc();
    return HomepageDetail(
      id: homepageId,
      title: '上下文主页',
      homepageType: 'university',
      status: 'published',
      sourceType: 'official_seed',
      claimStatus: 'unclaimed',
      categoryTags: const <String>['entity/campus'],
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final detail = await getHomepageDetail(homepageId);
    return HomepageShellData(homepage: detail);
  }

  @override
  Future<ObjectPageBundle> getObjectPageBundle(
    String homepageId, {
    String referralSource = '',
    String feedRequestId = '',
    String recommendationTraceId = '',
    String experimentBucket = '',
    String rolloutCohort = '',
  }) async {
    lastReferralSource = referralSource;
    lastFeedRequestId = feedRequestId;
    lastRecommendationTraceId = recommendationTraceId;
    lastExperimentBucket = experimentBucket;
    lastRolloutCohort = rolloutCohort;
    return ObjectPageBundle(
      objectType: 'homepage',
      objectId: homepageId,
      canonicalEntityId: 'entity:$homepageId',
      title: '上下文主页',
      objectPageTemplate: 'campus',
      tagRefs: const <String>['entity/campus'],
      stats: const <String, dynamic>{},
      intersectionReasons: const <IntersectionReason>[],
      highlightItems: const [],
      contentSections: const <String, dynamic>{},
      relatedObjects: const [],
      relationEdges: const [],
      assistantContext: ObjectPageContext(
        objectType: 'homepage',
        objectId: homepageId,
        canonicalEntityId: 'entity:$homepageId',
        tagRefs: const <String>['entity/campus'],
        entityRefs: <String>['entity:$homepageId'],
        relationEdgeIds: const <String>[],
        referralSource: referralSource,
        feedRequestId: feedRequestId,
        recommendationTraceId: recommendationTraceId,
        experimentBucket: experimentBucket,
        rolloutCohort: rolloutCohort,
      ),
      rolloutContext: ObjectPageRolloutContext(
        enabled: true,
        cohort: rolloutCohort,
        region: '',
        city: '',
        campus: '',
        appVersion: '',
        experimentBucket: experimentBucket,
        objectType: 'university',
        assistantProactiveEnabled: false,
        relationEvidenceEnabled: false,
      ),
    );
  }
}

/// WP3 打标形态仓库：bundle.tagRefs / detail.categoryTags 可注入
/// publish/tags 契约树全路径（Entity 类型 + Topic 地理/主题 + Format 载体）。
class _TaggedHomepageRepository extends MockHomepageRepository {
  _TaggedHomepageRepository({
    this.tagRefs = const <String>[
      'Entity/地点/景区/5A景区',
      'Topic/地理/行政区/四川省/成都市/都江堰市',
      'Topic/旅行/玩法/观光游览',
      'Format/内容角度/攻略',
    ],
    this.categoryTags = const <String>[],
  });

  final List<String> tagRefs;
  final List<String> categoryTags;

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final now = DateTime.now().toUtc();
    return HomepageDetail(
      id: homepageId,
      title: '打标主页',
      homepageType: 'sight',
      status: 'published',
      sourceType: 'official_seed',
      claimStatus: 'unclaimed',
      categoryTags: categoryTags,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final detail = await getHomepageDetail(homepageId);
    return HomepageShellData(homepage: detail);
  }

  @override
  Future<ObjectPageBundle> getObjectPageBundle(
    String homepageId, {
    String referralSource = '',
    String feedRequestId = '',
    String recommendationTraceId = '',
    String experimentBucket = '',
    String rolloutCohort = '',
  }) async {
    return ObjectPageBundle(
      objectType: 'homepage',
      objectId: homepageId,
      canonicalEntityId: 'entity:$homepageId',
      title: '打标主页',
      objectPageTemplate: 'travel_photo',
      tagRefs: tagRefs,
      stats: const <String, dynamic>{},
      intersectionReasons: const <IntersectionReason>[],
      highlightItems: const [],
      contentSections: const <String, dynamic>{},
      relatedObjects: const [],
      relationEdges: const [],
      assistantContext: ObjectPageContext(
        objectType: 'homepage',
        objectId: homepageId,
        canonicalEntityId: 'entity:$homepageId',
        tagRefs: tagRefs,
        entityRefs: <String>['entity:$homepageId'],
        relationEdgeIds: const <String>[],
        referralSource: referralSource,
        feedRequestId: feedRequestId,
        recommendationTraceId: recommendationTraceId,
        experimentBucket: experimentBucket,
        rolloutCohort: rolloutCohort,
      ),
      rolloutContext: ObjectPageRolloutContext(
        enabled: true,
        cohort: rolloutCohort,
        region: '',
        city: '',
        campus: '',
        appVersion: '',
        experimentBucket: experimentBucket,
        objectType: 'sight',
        assistantProactiveEnabled: false,
        relationEvidenceEnabled: false,
      ),
    );
  }
}

class _RecordingHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    return HomepageIntroduction(
      homepageId: homepageId,
      displayName: '西湖景区',
      homepageType: 'sight',
      summary: '真实 introduction summary',
      sections: <HomepageIntroductionSection>[
        HomepageIntroductionSection(
          kind: 'overview',
          title: '概况',
          bodyMarkdown: '真实 introduction summary',
          assets: const [],
          timelineItems: const [],
        ),
      ],
      relatedObjects: const [],
      sourceUrls: const [],
      updatedAt: '2026-06-12T00:00:00Z',
    );
  }
}

final class _StaticWishlistStateReader
    implements ContentEntityWishlistStateReader {
  const _StaticWishlistStateReader();

  @override
  Future<EntityWishlistState> getEntityWishlistState({
    required String objectId,
    required String objectKind,
  }) async {
    return EntityWishlistState(
      objectId: objectId,
      objectKind: objectKind,
      wishlisted: false,
    );
  }
}
