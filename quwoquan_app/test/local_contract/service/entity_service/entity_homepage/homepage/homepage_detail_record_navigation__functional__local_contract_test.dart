import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import '../../../../../support/runtime/homepage_source_cards_boundary_overrides.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show intersectionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentRuntimeConfigProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart'
    show buildProductionContentRuntimeConfigDefaults;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider, contentBehaviorTrackerProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal, HomepageIntroduction;

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

  testWidgets('实体记录卡进入 generated workBrowser 并透传来源与 feed trace', (
    tester,
  ) async {
    final behaviorTracker = ContentBehaviorTracker(
      reporter: RecordingContentBehaviorRepository(),
      enablePeriodicFlush: false,
    );
    addTearDown(behaviorTracker.dispose);
    // 本用例只验证记录卡路由语义；使用足够高的 viewport 让折叠头部后的首张记录卡
    // 可命中。折叠滚动几何由 homepage_detail_page_widget 的独立用例覆盖。
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final router = GoRouter(
      initialLocation: AppRoutePaths.homepageDetail(
        id: 'homepage_sight_west_lake',
      ),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
            '{id}',
            ':id',
          ),
          builder: (_, state) => HomepageDetailPage(
            homepageId: state.pathParameters['id'] ?? '',
            feedRequestId: 'feed-entity-1',
          ),
        ),
        GoRoute(
          path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
            '{workId}',
            ':workId',
          ),
          builder: (_, state) {
            final extra = state.extra as WorkBrowserEntryRouteExtra?;
            return Text(
              'WORK_TARGET:${state.pathParameters['workId']}:'
              '${state.uri.queryParameters['source']}:'
              '${extra?.referralSource.value}:${extra?.feedRequestId}',
            );
          },
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...homepageSourceCardsBoundaryOverrides(),
          authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            InMemoryIntersectionRepository(),
          ),
          contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const _EmptyIntroductionRepository(),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final cardFooter = find.text('湖畔慢行者');
    await tester.ensureVisible(cardFooter);
    await tester.pumpAndSettle();
    await tester.tap(cardFooter);
    await tester.pumpAndSettle();
    expect(
      find.text(
        'WORK_TARGET:west_lake_record_1:'
        'entity_page:entity_page:feed-entity-1',
      ),
      findsOneWidget,
    );
  });
}

class _EmptyIntroductionRepository implements HomepageIntroductionRepository {
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

class _NoNetworkHttpOverrides extends HttpOverrides {}

final class _GuestHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
