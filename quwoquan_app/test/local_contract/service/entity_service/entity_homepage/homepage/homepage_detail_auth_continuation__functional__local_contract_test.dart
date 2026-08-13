import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/subject_follow/application/public/subject_follow_writer.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ObjectHomepageText, ProfileText;
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider, intersectionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentRuntimeConfigProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart'
    show buildProductionContentRuntimeConfigDefaults;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show
        homepageReviewCommandWriterProvider,
        homepageReviewQueryProvider,
        homepageSubjectFollowCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider, contentBehaviorTrackerProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage_review/homepage_review_facets_typed_double.dart';

const String _homepageId = 'homepage_sight_west_lake';

List<Override> _homepageShellBoundaryOverrides() => <Override>[
  ...sealedCloudBoundaryOverrides(),
  behaviorRepositoryProvider.overrideWithValue(
    RecordingContentBehaviorRepository(),
  ),
  intersectionRepositoryProvider.overrideWithValue(
    InMemoryIntersectionRepository(),
  ),
  contentRuntimeConfigProvider.overrideWithValue(
    buildProductionContentRuntimeConfigDefaults(),
  ),
];

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    AuthGate.resetDebounce();
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
    AuthGate.resetDebounce();
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('登录成功后一次性续接实体主页关注', (tester) async {
    final followWriter = _RecordingSubjectFollowWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(
            _UniversityHomepageRepository(),
          ),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageSubjectFollowCommandWriterProvider.overrideWithValue(
            followWriter,
          ),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomepageDetailPage)),
    );
    container
        .read(authContinuationProvider.notifier)
        .set(const FollowHomepageContinuation(homepageId: _homepageId));

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableHomepageSession)
        .loginNow();
    await tester.pumpAndSettle();

    expect(followWriter.followCalls, 1);
    expect(followWriter.lastSubjectId, _homepageId);
    expect(container.read(authContinuationProvider), isNull);
    await tester.pump();
    expect(followWriter.followCalls, 1, reason: '关注续接必须 one-shot');
  });

  testWidgets('登录成功后一次性续接实体主页想去意图', (tester) async {
    final reporter = _RecordingBehaviorReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomepageDetailPage)),
    );
    container
        .read(authContinuationProvider.notifier)
        .set(const WishlistHomepageContinuation(homepageId: _homepageId));

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableHomepageSession)
        .loginNow();
    await tester.pumpAndSettle();

    expect(reporter.events, hasLength(1));
    expect(reporter.events.single.action, BehaviorEventType.wishlistAdd);
    expect(reporter.events.single.objectId, _homepageId);
    expect(container.read(authContinuationProvider), isNull);
    await tester.pump();
    expect(reporter.events, hasLength(1), reason: '想去续接必须 one-shot');
    // 想去即时反馈（诚实态 toast）自动消隐计时器走完，避免尾部 pending timer。
    expect(
      find.text(ObjectHomepageText.wishlistAddedFeedback),
      findsOneWidget,
      reason: '无交集时只确认动作本身，不伪造同行者',
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('登录成功后切换到口碑子页并续接评价编辑器', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final reviews = InMemoryHomepageReviewFacet(
      activePersonaId: 'persona-homepage-test',
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageReviewQueryProvider.overrideWithValue(reviews),
          homepageReviewCommandWriterProvider.overrideWithValue(reviews),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomepageDetailPage)),
    );
    container
        .read(authContinuationProvider.notifier)
        .set(
          const OpenHomepageReviewComposerContinuation(homepageId: _homepageId),
        );

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableHomepageSession)
        .loginNow();
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('homepage-review-sheet')),
      findsOneWidget,
    );
    expect(container.read(authContinuationProvider), isNull);
  });

  testWidgets('在这里发起以实体为来源引用进入行动创建', (tester) async {
    GatheringCreateNavigationRequest? captured;
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(id: _homepageId),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) =>
              HomepageDetailPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
        GoRoute(
          path: AppRoutePaths.gatheringCreate,
          builder: (_, state) {
            captured = state.extra as GatheringCreateNavigationRequest?;
            return const Text('CREATE', textDirection: TextDirection.ltr);
          },
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.entityActionStartGathering),
      findsOneWidget,
      reason: '可到访地点类主页提供「在这里发起」（发起不依赖交集存在）',
    );
    await tester.tap(find.text(ObjectHomepageText.entityActionStartGathering));
    await tester.pumpAndSettle();

    expect(find.text('CREATE'), findsOneWidget);
    expect(captured, isNotNull);
    expect(captured!.actionKey, 'start_gathering');
    expect(captured!.sourceRefs, hasLength(1));
    expect(captured!.sourceRefs.single.objectId, _homepageId);
    expect(captured!.sourceRefs.single.objectKind, 'homepage');
    expect(captured!.targetObject.objectId, _homepageId);
    expect(captured!.targetObject.routeId, 'homepageDetail');
  });

  testWidgets('私信认领主体进入 owner 主页并携带私信分流意图', (tester) async {
    // 私信 Owner 不再直建会话：统一进入 owner 主页并由主页既有的
    // 关系能力位分流（canOpen→会话 / canGreet→打招呼），避免绕过
    // conversation-entry 矩阵撞 greeting_required。
    String? capturedHandle;
    UserProfileRouteExtra? capturedExtra;
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(id: _homepageId),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) =>
              HomepageDetailPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
        GoRoute(
          path: AppRoutePaths.userProfilePathTemplate.replaceAll(
            '{userHandle}',
            ':userHandle',
          ),
          builder: (_, state) {
            capturedHandle = state.pathParameters['userHandle'];
            capturedExtra = state.extra as UserProfileRouteExtra?;
            return const Text(
              'OWNER_PROFILE',
              textDirection: TextDirection.ltr,
            );
          },
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(
            _ClaimedHomepageRepository(),
          ),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text(ProfileText.profileDirectMessage), findsOneWidget);

    await tester.tap(find.text(ProfileText.profileDirectMessage));
    await tester.pumpAndSettle();

    expect(find.text('OWNER_PROFILE'), findsOneWidget);
    expect(capturedHandle, 'owner-persona-1');
    expect(capturedExtra?.safePersonaId, 'owner-persona-1');
    expect(capturedExtra?.openMessageComposer, isTrue);
  });

  testWidgets('游客关闭地点主页想去登录后留在公开详情且清除续接', (tester) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(id: _homepageId),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) =>
              HomepageDetailPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => TextButton(
            key: const ValueKey<String>('homepage-detail-login-close'),
            onPressed: () {
              ProviderScope.containerOf(
                context,
              ).read(authContinuationProvider.notifier).clear();
              context.go(
                state.uri.queryParameters[loginDismissFallbackQueryParam] ??
                    AppRoutePaths.home,
              );
            },
            child: const Text('CLOSE_LOGIN'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ..._homepageShellBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(
            _FlippableHomepageSession.new,
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          currentUserIdProvider.overrideWithValue(''),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text(ObjectHomepageText.homepageWishlistAction));
    await tester.pumpAndSettle();

    final loginContext = tester.element(
      find.byKey(const ValueKey<String>('homepage-detail-login-close')),
    );
    expect(
      GoRouterState.of(
        loginContext,
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-detail-login-close')),
    );
    await tester.pumpAndSettle();
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('homepage-detail-login-close')),
      findsNothing,
    );
    expect(
      find.text(ObjectHomepageText.homepageWishlistAction),
      findsOneWidget,
    );
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomepageDetailPage)),
    );
    expect(container.read(authContinuationProvider), isNull);
  });
}

final class _FlippableHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'homepage-access-token',
      refreshToken: 'homepage-refresh-token',
      ownerId: 'homepage-viewer-owner',
      activePersonaId: 'homepage-viewer-persona',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'homepage-install-id',
    );
  }
}

final class _RecordingSubjectFollowWriter implements SubjectFollowWriter {
  int followCalls = 0;
  String? lastSubjectId;

  @override
  Future<SubjectFollowCommandResult> follow(
    FollowSubjectCommand command,
  ) async {
    followCalls += 1;
    lastSubjectId = command.subjectId;
    return SubjectFollowCommandResult(
      personaId: 'homepage-viewer-persona',
      subjectType: command.subjectType,
      subjectId: command.subjectId,
      state: SubjectFollowState.following,
      idempotentReplay: false,
      updatedAt: DateTime.utc(2026, 7, 15),
    );
  }

  @override
  Future<SubjectFollowCommandResult> unfollow(
    UnfollowSubjectCommand command,
  ) async {
    return SubjectFollowCommandResult(
      personaId: 'homepage-viewer-persona',
      subjectType: command.subjectType,
      subjectId: command.subjectId,
      state: SubjectFollowState.unfollowed,
      idempotentReplay: false,
      updatedAt: DateTime.utc(2026, 7, 15),
    );
  }
}

final class _RecordingBehaviorReporter implements BehaviorReporter {
  final List<BehaviorEvent> events = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    this.events.addAll(events);
  }
}

final class _UniversityHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final detail = await super.getHomepageDetail(homepageId);
    return detail.copyWith(homepageType: 'university');
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final detail = await getHomepageDetail(homepageId);
    return HomepageShellData(homepage: detail);
  }
}

final class _ClaimedHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final detail = await super.getHomepageDetail(homepageId);
    return detail.copyWith(
      claimStatus: 'claimed',
      ownerUserId: 'owner-user-1',
      ownerPersonaId: 'owner-persona-1',
    );
  }
}

final class _NoNetworkHttpOverrides extends HttpOverrides {}
