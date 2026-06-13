import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_context.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_rollout_context.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';

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
      const ProviderScope(
        child: MaterialApp(
          home: HomepageDetailPage(homepageId: 'homepage_sight_west_lake'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('西湖景区'), findsWidgets);
    expect(find.text(UITextConstants.objectConnectionWithYou), findsOneWidget);
    expect(find.text('从主页发内容'), findsOneWidget);
    expect(find.text('与你相关'), findsOneWidget);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(find.text('内容'), findsWidgets);
    expect(find.text('讨论'), findsWidgets);
    expect(find.text('兴趣圈'), findsOneWidget);
    expect(find.text('认识西湖景区'), findsOneWidget);
    expect(find.text('实体介绍'), findsNothing);
    expect(find.text(UITextConstants.objectIntroMoreLabel), findsOneWidget);
    expect(find.text('认领主页'), findsWidgets);
    expect(find.text('治理入口'), findsNothing);
  });

  testWidgets('选择模式显示 attach 按钮', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
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

  testWidgets('alpha/mock 下支持数据工程 entityRef 直达实体主页', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: HomepageDetailPage(homepageId: 'Entity/旅行/景区/峨眉山'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('峨眉山'), findsWidgets);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('对象页 bundle 请求透传推荐与灰度上下文', (tester) async {
    final repository = _RecordingHomepageRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homepageRepositoryProvider.overrideWithValue(repository),
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
    expect(find.text('从主页发内容'), findsOneWidget);
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
          homepageIntroductionRepositoryProvider.overrideWithValue(
            _RecordingHomepageIntroductionRepository(),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('真实 introduction summary'), findsOneWidget);
    final introButton = find.byKey(
      const ValueKey<String>('homepage-introduction-entry-button'),
    );
    await tester.ensureVisible(introButton);
    await tester.pumpAndSettle();
    tester.widget<CupertinoButton>(introButton).onPressed?.call();
    await tester.pumpAndSettle();
    expect(find.text('介绍页:homepage_sight_west_lake'), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

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
      assistantContext: ObjectPageContext(
        objectType: 'homepage',
        objectId: homepageId,
        canonicalEntityId: 'entity:$homepageId',
        referralSource: referralSource,
        feedRequestId: feedRequestId,
        recommendationTraceId: recommendationTraceId,
        experimentBucket: experimentBucket,
        rolloutCohort: rolloutCohort,
      ),
      rolloutContext: ObjectPageRolloutContext(
        enabled: true,
        cohort: rolloutCohort,
        experimentBucket: experimentBucket,
        objectType: 'university',
      ),
    );
  }
}

class _RecordingHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId,
  ) async {
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
        ),
      ],
      sourceRefs: const <String>['fixture:introduction'],
      updatedAt: '2026-06-12T00:00:00Z',
    );
  }
}
