import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/micro_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';
import 'package:quwoquan_app/ui/discovery/widgets/dual_column_discovery_post_card.dart';
import 'package:quwoquan_app/ui/discovery/widgets/intersection_spotlight_module.dart';

MicroPostDto _post() {
  return MicroPostDto(
    id: 'post_intersection_demo',
    type: 'moment',
    identity: 'moment',
    authorId: 'user_demo',
    displayName: '小趣用户',
    avatarUrl: '',
    assistantUsePolicy: 'allow',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    createdAt: DateTime(2026),
    body: '川西雪山和校园摄影路线',
    imageUrls: const <String>[''],
    intersectionReasons: <IntersectionReason>[
      IntersectionReason(
        dimension: 'interest',
        tagRefs: <String>['Topic/旅行'],
        relationKind: 'place',
        displayText: '都在看川西攻略',
        actionType: 'follow',
        actionTargetId: 'entity_chuanxi',
        sharedCount: 8,
        intersectionPoints: <IntersectionPoint>[
          IntersectionPoint(
            pointId: 'post_ix_1',
            pointClass: 'fact',
            dimension: 'interest',
            displayText: '都在看川西攻略',
          ),
        ],
        factPointCount: 1,
        totalPointCount: 1,
      ),
    ],
  );
}

void main() {
  testWidgets('双列发现卡展示短交集理由并响应点击', (tester) async {
    var tapped = false;
    var liked = false;
    await tester.binding.setSurfaceSize(const Size(390, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 180,
            child: DualColumnDiscoveryPostCard(
              item: _post(),
              isDark: false,
              isLiked: false,
              likeCount: 12,
              onTap: () => tapped = true,
              onUserTap: () {},
              onLikeTap: () => liked = true,
            ),
          ),
        ),
      ),
    );

    // 新口径：最强证据组短句（count 为 0 时仅短句，零内部词）。
    expect(find.text('都在看川西攻略'), findsOneWidget);
    expect(find.textContaining('个交集点'), findsNothing);
    expect(find.text('川西雪山和校园摄影路线'), findsOneWidget);
    await tester.tap(find.byType(DualColumnDiscoveryPostCard));
    expect(tapped, isTrue);
    await tester.tap(find.byIcon(CupertinoIcons.heart));
    expect(liked, isTrue);
  });

  testWidgets('双列发现卡结构：封面 → 理由 → 标题 → 作者行，理由不覆盖封面', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 180,
            child: DualColumnDiscoveryPostCard(
              item: _post(),
              isDark: false,
              isLiked: false,
              likeCount: 12,
              onTap: () {},
              onUserTap: () {},
              onLikeTap: () {},
            ),
          ),
        ),
      ),
    );

    final cover = find.byKey(DualColumnDiscoveryPostCard.coverKey);
    final reasonSlot = find.byKey(DualColumnDiscoveryPostCard.reasonSlotKey);
    final title = find.byKey(DualColumnDiscoveryPostCard.titleKey);
    final authorRow = find.byKey(DualColumnDiscoveryPostCard.authorRowKey);
    expect(cover, findsOneWidget);
    expect(reasonSlot, findsOneWidget);
    expect(title, findsOneWidget);
    expect(authorRow, findsOneWidget);

    final coverTop = tester.getTopLeft(cover).dy;
    final reasonTop = tester.getTopLeft(reasonSlot).dy;
    final titleTop = tester.getTopLeft(title).dy;
    final authorTop = tester.getTopLeft(authorRow).dy;
    expect(coverTop, lessThan(reasonTop));
    expect(reasonTop, lessThan(titleTop));
    expect(titleTop, lessThan(authorTop));

    expect(
      find.descendant(of: cover, matching: find.byType(IntersectionReasonChip)),
      findsNothing,
    );
    final coverBox = tester.renderObject<RenderBox>(cover);
    final reasonBox = tester.renderObject<RenderBox>(reasonSlot);
    expect(
      tester.getTopLeft(reasonSlot).dy,
      greaterThanOrEqualTo(tester.getTopLeft(cover).dy + coverBox.size.height),
    );
    expect(reasonBox.size.height, greaterThan(0));
  });

  testWidgets('双列发现卡在窄宽度下不发生右侧溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    FlutterErrorDetails? overflow;
    final oldOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('A RenderFlex overflowed')) {
        overflow = details;
      }
      oldOnError?.call(details);
    };
    addTearDown(() => FlutterError.onError = oldOnError);

    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: SizedBox(
            width: 132,
            child: DualColumnDiscoveryPostCard(
              item: _post(),
              isDark: false,
              isLiked: false,
              likeCount: 12345,
              onTap: () {},
              onUserTap: () {},
              onLikeTap: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(overflow, isNull);
  });

  testWidgets('单列关系卡结构：作者头部 → 交集 → 正文 → 媒体 → 赞转评', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          discoveryFeedMapProvider.overrideWith(
            () => _SinglePostFeedMapNotifier(_post()),
          ),
        ],
        child: CupertinoApp(
          home: HomeMultiFormFeed(
            isDark: false,
            channelId: 'moment',
            template: 'single_column_relations',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
          ),
        ),
      ),
    );
    await tester.pump();

    const headerKey = ValueKey('home-relation-card-header');
    const reasonKey = ValueKey('home-relation-card-reason');
    const bodyKey = ValueKey('home-relation-card-body');
    const mediaKey = ValueKey('home-relation-card-media');
    const actionsKey = ValueKey('home-relation-card-actions');
    final header = find.byKey(headerKey);
    final reason = find.byKey(reasonKey);
    final body = find.byKey(bodyKey);
    final media = find.byKey(mediaKey);
    final actions = find.byKey(actionsKey);
    expect(header, findsOneWidget);
    expect(reason, findsOneWidget);
    expect(body, findsOneWidget);
    expect(media, findsOneWidget);
    expect(actions, findsOneWidget);

    expect(
      tester.getTopLeft(header).dy,
      lessThan(tester.getTopLeft(reason).dy),
    );
    expect(tester.getTopLeft(reason).dy, lessThan(tester.getTopLeft(body).dy));
    expect(tester.getTopLeft(body).dy, lessThan(tester.getTopLeft(media).dy));
    expect(
      tester.getTopLeft(media).dy,
      lessThan(tester.getTopLeft(actions).dy),
    );

    expect(
      find.descendant(of: actions, matching: find.byType(CupertinoButton)),
      findsNWidgets(3),
    );
    expect(find.textContaining('收藏'), findsNothing);
    expect(find.textContaining('稍后看'), findsNothing);
    expect(find.textContaining('关注内容'), findsNothing);
  });

  testWidgets('交集 spotlight 曝光上报前 4 条并写 impression 归因', (tester) async {
    final intersectionRepo = _RecordingIntersectionRepository();
    final behaviorRepo = MockBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      repository: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          intersectionRepositoryProvider.overrideWithValue(intersectionRepo),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: CupertinoApp(
          home: HomeMultiFormFeed(
            isDark: false,
            channelId: 'moment',
            template: 'single_column_relations',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(intersectionRepo.reportedObjectIds, <String>[
      'object_0',
      'object_1',
      'object_2',
      'object_3',
    ]);
    final impressions = behaviorRepo.recorded
        .where(
          (event) =>
              event.action == BehaviorAction.impression &&
              (event.intersectionId ?? '').isNotEmpty,
        )
        .toList(growable: false);
    expect(impressions, hasLength(4));
    expect(impressions.first.contentId, 'object_0');
    expect(impressions.first.referralSource, ReferralSource.organicFeed);
    expect(impressions.first.intersectionId, 'ix_object_0');
    expect(impressions.first.intersectionDimension, 'relationship');
    expect(impressions.first.intersectionClass, 'fact');
  });

  testWidgets('单列内容卡 impression/click 透传 position 和 referralSource', (
    tester,
  ) async {
    final behaviorRepo = MockBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      repository: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    var opened = false;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          discoveryFeedMapProvider.overrideWith(
            () => _SinglePostFeedMapNotifier(_post()),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _EmptyIntersectionRepository(),
          ),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: CupertinoApp(
          home: HomeMultiFormFeed(
            isDark: false,
            channelId: 'moment',
            template: 'single_column_relations',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
            onPostTap: (_, _, {feedPosts}) => opened = true,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final impressions = behaviorRepo.recorded
        .where(
          (event) =>
              event.action == BehaviorAction.impression &&
              event.contentId == 'post_intersection_demo',
        )
        .toList(growable: false);
    expect(impressions, hasLength(1));
    expect(impressions.single.contentId, 'post_intersection_demo');
    expect(impressions.single.position, 0);
    expect(impressions.single.referralSource, ReferralSource.organicFeed);

    await tester.tap(find.byKey(const ValueKey('home-relation-card-media')));
    await tester.pump();
    expect(opened, isTrue);
    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorAction.click)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    expect(clicks.single.contentId, 'post_intersection_demo');
    expect(clicks.single.position, 0);
    expect(clicks.single.referralSource, ReferralSource.organicFeed);
    expect(clicks.single.feedRequestId, isNotEmpty);
  });

  testWidgets('交集 spotlight 只展示可行动对象（高保横滑头像卡：名字+主副交集）', (tester) async {
    var opened = false;
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      CupertinoApp(
        home: IntersectionSpotlightModule(
          isDark: false,
          reasons: <IntersectionReason>[
            // 无 actionTargetId：不可行动，应被过滤。
            IntersectionReason(displayName: '仅解释无目标'),
            IntersectionReason(
              dimension: 'interest',
              intersectionClass: 'affinity',
              relationKind: 'circle',
              objectKind: 'circle',
              displayName: '摄影圈',
              displayText: '共同关注摄影内容',
              primaryText: '共同关注摄影内容',
              secondaryText: '12 位摄影同好在这里',
              confidenceLabel: '推荐',
              actionType: 'join_circle',
              actionTargetId: 'circle_photo',
              sharedCount: 0,
              intersectionPoints: <IntersectionPoint>[
                IntersectionPoint(
                  pointId: 'ix_photo_point',
                  pointClass: 'recommended',
                  dimension: 'interest',
                  label: '摄影内容相似',
                  displayText: '共同关注摄影内容',
                ),
              ],
              recommendedPointCount: 1,
              totalPointCount: 1,
              pointClassLabel: '推荐交集',
            ),
          ],
          onReasonTap: (_) => opened = true,
        ),
      ),
    );

    // 高保头像卡：对象名 + 云侧主交集结论句（蓝）+ 副交集说明（灰）；
    // 对象角标以语义 label 暴露，推荐状态只显示新鲜小蓝点，不新增文字事实。
    // 零内部词、零空数字（count=0 不显示「0」）。
    expect(find.text('摄影圈'), findsOneWidget);
    expect(find.text('共同关注摄影内容'), findsOneWidget);
    expect(find.text('12 位摄影同好在这里'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (widget) => widget is Semantics && widget.properties.label == '圈',
      ),
      findsOneWidget,
    );
    expect(find.text('推荐'), findsNothing);
    expect(find.textContaining('个推荐交集点'), findsNothing);
    expect(find.text('0 共同点'), findsNothing);
    expect(find.text('仅解释无目标'), findsNothing);
    expect(
      IntersectionSpotlightModule.visibleCardsPerViewport,
      inInclusiveRange(3, 3.5),
    );
    final primary = tester.widget<Text>(
      find.byKey(IntersectionSpotlightModule.primaryTextKey),
    );
    final secondary = tester.widget<Text>(
      find.byKey(IntersectionSpotlightModule.secondaryTextKey),
    );
    final primaryContext = tester.element(
      find.byKey(IntersectionSpotlightModule.primaryTextKey),
    );
    final secondaryContext = tester.element(
      find.byKey(IntersectionSpotlightModule.secondaryTextKey),
    );
    expect(primary.maxLines, 1);
    expect(secondary.maxLines, 1);
    expect(primary.style?.color, AppColors.iosAccent(primaryContext));
    expect(
      secondary.style?.color,
      AppColors.iosSecondaryLabel(secondaryContext),
    );
    await tester.tap(find.text('摄影圈'), warnIfMissed: false);
    await tester.pump();
    expect(opened, isTrue);
  });

  testWidgets('交集 spotlight 在窄宽度下不发生底部 overflow', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    FlutterErrorDetails? overflow;
    final oldOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('A RenderFlex overflowed')) {
        overflow = details;
      }
      oldOnError?.call(details);
    };
    addTearDown(() => FlutterError.onError = oldOnError);

    await tester.pumpWidget(
      CupertinoApp(
        home: SizedBox(
          width: 320,
          child: IntersectionSpotlightModule(
            isDark: false,
            reasons: <IntersectionReason>[
              IntersectionReason(
                dimension: 'relationship',
                relationKind: 'circle',
                objectKind: 'circle',
                displayName: '摄影圈摄影圈摄影圈',
                displayText: '共同关注摄影内容',
                primaryText: '共同关注特别多并且最近一起活跃',
                secondaryText: '老同学 李航和周屿都在这里',
                actionType: 'join_circle',
                actionTargetId: 'circle_photo',
                intersectionId: 'ix_circle_photo',
                intersectionPoints: <IntersectionPoint>[
                  IntersectionPoint(
                    pointId: 'ix_photo_point_fact',
                    pointClass: 'fact',
                    dimension: 'relationship',
                    label: '共同关注特别多并且最近一起活跃',
                    displayText: '共同关注特别多并且最近一起活跃',
                    count: 12,
                    sampleText: '老同学 李航和周屿都在这里',
                  ),
                ],
                factPointCount: 1,
                totalPointCount: 1,
              ),
            ],
            onReasonTap: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(overflow, isNull);
  });

  testWidgets('交集 spotlight「换一批」：候选窗内轮转出下一批对象', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    IntersectionReason cover(String id, String name) => IntersectionReason(
      dimension: 'relationship',
      relationKind: 'person',
      objectKind: 'person',
      displayName: name,
      primaryText: '共同关注 3 人',
      actionType: 'view_object',
      actionTargetId: id,
      intersectionId: 'ix_$id',
      intersectionPoints: <IntersectionPoint>[
        IntersectionPoint(
          pointId: '${id}_p',
          pointClass: 'fact',
          dimension: 'relationship',
          label: '共同关注',
          displayText: '共同关注',
          count: 3,
        ),
      ],
    );

    await tester.pumpWidget(
      CupertinoApp(
        home: IntersectionSpotlightModule(
          isDark: false,
          windowSize: 2,
          reasons: <IntersectionReason>[
            cover('a', '阿一'),
            cover('b', '阿二'),
            cover('c', '阿三'),
            cover('d', '阿四'),
          ],
          onReasonTap: (_) {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 第一屏：前 2 个对象（windowSize=2）。
    expect(find.text('阿一'), findsOneWidget);
    expect(find.text('阿二'), findsOneWidget);

    // 候选窗 > windowSize → 出现「换一批」。
    final shuffle = find.byKey(IntersectionSpotlightModule.shuffleKey);
    expect(shuffle, findsOneWidget);

    await tester.tap(shuffle);
    await tester.pumpAndSettle();

    // 换一批后轮转到下一批（看过的保留在候选窗，只是被顶替展示）。
    expect(find.text('阿三'), findsOneWidget);
    expect(find.text('阿四'), findsOneWidget);
  });
}

class _SinglePostFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _SinglePostFeedMapNotifier(this.post);

  final MicroPostDto post;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'moment': AsyncData(DiscoveryFeedState(items: <MicroPostDto>[post])),
    };
  }

  @override
  Future<void> load(String channelId, {bool force = false}) async {}
}

class _RecordingIntersectionRepository implements IntersectionRepository {
  final List<String> reportedObjectIds = <String>[];

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    return List<IntersectionReason>.generate(
      6,
      (index) => IntersectionReason(
        intersectionId: 'ix_object_$index',
        dimension: 'relationship',
        intersectionClass: 'fact',
        relationKind: 'person',
        objectKind: 'person',
        displayName: '对象$index',
        primaryText: '共同关注的人',
        actionType: 'view_object',
        actionTargetId: 'object_$index',
      ),
    );
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {
    reportedObjectIds.addAll(objectIds);
  }

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async {
    return const <IntersectionReason>[];
  }
}

class _EmptyIntersectionRepository implements IntersectionRepository {
  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {}

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async {
    return const <IntersectionReason>[];
  }
}
