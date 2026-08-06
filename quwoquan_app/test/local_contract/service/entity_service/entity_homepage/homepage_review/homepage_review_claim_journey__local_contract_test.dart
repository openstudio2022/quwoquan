import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show
        homepageClaimRequestCommandWriterProvider,
        homepageFacetSetProvider,
        homepageWriteTargetReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailEntityWishlistStateReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show homepageReviewCommandWriterProvider, homepageReviewQueryProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider, contentBehaviorTrackerProvider;
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryReporterProvider;
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/presentation/homepage_claim_page.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        EntityWishlistState,
        HomepageClaimRequestView,
        HomepageIntroduction,
        HomepageReviewListQuery;
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage_review/homepage_review_facets_typed_double.dart';

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

const String _homepageId = 'homepage_sight_west_lake';

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
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('浏览主页后写评价并从治理菜单提交认领申请', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final homepage = _JourneyHomepageRepository();
    final reviews = InMemoryHomepageReviewFacet(
      activePersonaId: 'persona_entity_uat',
      clock: () => DateTime.utc(2026, 7, 20, 10),
    );
    const wishlistStateReader = _NoWishlistStateReader();
    final telemetry = RecordingAppTelemetryRecorder();
    final behaviorRepository = RecordingContentBehaviorRepository();
    final behaviorTracker = ContentBehaviorTracker(
      reporter: behaviorRepository,
      enablePeriodicFlush: false,
    );
    addTearDown(behaviorTracker.dispose);
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(id: _homepageId),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) => HomepageDetailPage(
            homepageId: state.pathParameters['id'] ?? '',
            feedRequestId: 'feed-entity-uat',
          ),
        ),
        GoRoute(
          path: AppRoutePaths.homepageClaimPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) =>
              HomepageClaimPage(homepageId: state.pathParameters['id'] ?? ''),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedEntitySession.new,
          ),
          currentUserIdProvider.overrideWithValue(''),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'persona_entity_uat',
              ownerUserId: 'user_entity_uat',
              subjectType: 'persona',
              displayName: '实体旅程用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(homepage),
          homepageWriteTargetReaderProvider.overrideWithValue(homepage),
          homepageClaimRequestCommandWriterProvider.overrideWithValue(homepage),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const _EmptyIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            wishlistStateReader,
          ),
          homepageReviewQueryProvider.overrideWithValue(reviews),
          homepageReviewCommandWriterProvider.overrideWithValue(reviews),
          behaviorRepositoryProvider.overrideWithValue(behaviorRepository),
          contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
          appTelemetryReporterProvider.overrideWithValue(telemetry),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    // Given：真实详情页已加载 canonical 主页。
    final renderedTexts = tester
        .widgetList<Text>(find.byType(Text))
        .map((widget) => widget.data)
        .whereType<String>()
        .toList(growable: false);
    expect(
      renderedTexts.any((text) => text.contains('西湖')),
      isTrue,
      reason: 'rendered texts: $renderedTexts',
    );

    // When：切到口碑子页并完成评价。
    final opinion = find.byKey(
      const ValueKey<String>('homepage-content-filter-option-opinion'),
    );
    await Scrollable.ensureVisible(opinion.evaluate().single, alignment: 0.35);
    await tester.pumpAndSettle();
    await tester.tap(opinion);
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-write-entry')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-star-5')),
    );
    await tester.enterText(
      find.byKey(const ValueKey<String>('homepage-review-body-field')),
      '实体主页商用旅程评价',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-submit')),
    );
    await tester.pumpAndSettle();

    final reviewPage = await reviews.listByHomepage(
      HomepageReviewListQuery(homepageId: _homepageId),
    );
    expect(reviewPage.items, hasLength(1));
    expect(reviewPage.items.single.rating, 5);
    expect(reviewPage.items.single.body, '实体主页商用旅程评价');

    // And：从详情页治理菜单进入认领页，提交最小合法材料后返回详情。
    await tester.tap(find.byKey(const ValueKey<String>('object-chrome-more')));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ObjectHomepageText.homepageClaimAction));
    await tester.pumpAndSettle();
    expect(find.byType(HomepageClaimPage), findsOneWidget);

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '13800000000',
    );
    await tester.tap(find.text(ObjectHomepageText.homepageClaimSubmit));
    await tester.pumpAndSettle();

    expect(homepage.claimCreateCalls, 1);
    expect(homepage.lastClaimDraft?.contactPhone, '13800000000');
    expect(find.byType(HomepageDetailPage), findsOneWidget);
    expect(
      telemetry.recorded.any(
        (event) =>
            event.action == 'claim_request_submit' &&
            event.extensions['result'] == 'success',
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _JourneyHomepageRepository extends MockHomepageRepository {
  int claimCreateCalls = 0;
  HomepageClaimRequestDraft? lastClaimDraft;

  @override
  Future<HomepageClaimRequestView> createClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    claimCreateCalls += 1;
    lastClaimDraft = draft;
    return super.createClaimRequest(homepageId: homepageId, draft: draft);
  }
}

final class _AuthenticatedEntitySession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'entity-uat-token',
    refreshToken: 'entity-uat-refresh-token',
    ownerId: 'user_entity_uat',
    activePersonaId: 'persona_entity_uat',
  );
}

final class _EmptyIntroductionRepository
    implements HomepageIntroductionRepository {
  const _EmptyIntroductionRepository();

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    return null;
  }
}

final class _NoWishlistStateReader implements ContentEntityWishlistStateReader {
  const _NoWishlistStateReader();

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

final class _NoNetworkHttpOverrides extends HttpOverrides {}
