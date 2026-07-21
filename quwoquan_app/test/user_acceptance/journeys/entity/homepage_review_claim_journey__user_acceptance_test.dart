import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import '../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_claim_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        EntityWishlistState,
        HomepageReviewListQuery;
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

import '../../../support/recording_app_telemetry_recorder.dart';

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
    final reviews = AlphaHomepageReviewFacet(
      activePersonaId: 'persona_entity_uat',
      clock: () => DateTime.utc(2026, 7, 20, 10),
    );
    const wishlistStateReader = _NoWishlistStateReader();
    final telemetry = RecordingAppTelemetryRecorder();
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
              subAccountId: 'persona_entity_uat',
              ownerUserId: 'user_entity_uat',
              subjectType: 'persona',
              displayName: '实体旅程用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(homepage),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const _EmptyIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            wishlistStateReader,
          ),
          homepageReviewQueryProvider.overrideWithValue(reviews),
          homepageReviewCommandWriterProvider.overrideWithValue(reviews),
          appTelemetryReporterProvider.overrideWithValue(telemetry),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    // Given：真实详情页已加载 canonical 主页。
    expect(find.textContaining('西湖'), findsWidgets);

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
    await tester.tap(find.text(UITextConstants.homepageClaimAction));
    await tester.pumpAndSettle();
    expect(find.byType(HomepageClaimPage), findsOneWidget);

    await tester.enterText(
      find.byType(CupertinoTextField).first,
      '13800000000',
    );
    await tester.tap(find.text(UITextConstants.homepageClaimSubmit));
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
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    claimCreateCalls += 1;
    lastClaimDraft = draft;
    return super.createHomepageClaimRequest(
      homepageId: homepageId,
      draft: draft,
    );
  }
}

final class _AuthenticatedEntitySession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'entity-uat-token',
    ownerId: 'user_entity_uat',
    activeSubAccountId: 'persona_entity_uat',
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
