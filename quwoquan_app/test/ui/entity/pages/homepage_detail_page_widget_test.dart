import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_context.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_rollout_context.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
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
    expect(find.text('你和这里的交集'), findsOneWidget);
    expect(find.text('问小趣'), findsOneWidget);
    expect(find.text('与你相关'), findsOneWidget);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(find.text('首页'), findsOneWidget);
    expect(find.text('内容'), findsWidgets);
    expect(find.text('口碑'), findsWidgets);
    expect(find.text('关联'), findsOneWidget);
    expect(find.text('统一对象键'), findsOneWidget);
    expect(find.text('对象页模板'), findsOneWidget);
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

  testWidgets('对象页 bundle 请求透传推荐与灰度上下文', (tester) async {
    final repository = _RecordingHomepageRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [homepageRepositoryProvider.overrideWithValue(repository)],
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
    expect(find.text('问小趣'), findsOneWidget);
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
