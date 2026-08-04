// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/domain/discovery_feed_page.dart';
import 'package:quwoquan_app/content/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/content/content/post/domain/home_feed_scroll_anchor.dart';
import 'package:quwoquan_app/content/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/content/content/post/application/home_feed_scroll_anchor_provider.dart';
import 'package:quwoquan_app/content/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        ContentPostProjection,
        FeedObjectCard;

import '../../../support/cloud_services/behavior_repository_double.dart';

ContentPostViewData _post(String channel, int index, {int bodyRepeats = 1}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: '${channel}_anchor_post_$index',
      contentType: 'micro',
      contentIdentity: 'moment',
      authorId: '${channel}_author_$index',
      authorDisplayName: 'Anchor Author $index',
      authorAvatarUrl: '',
      authorBackgroundUrl: null,
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      assistantUsePolicy: 'allow',
      likeCount: index,
      commentCount: index,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 7, 28),
      updatedAt: null,
      publishedAt: null,
      body: List<String>.filled(
        bodyRepeats,
        'Stable channel anchor post $index keeps enough body text to produce '
        'a deterministic single-column card height during the widget test.',
      ).join(' '),
      mediaUrls: const <String>[],
      intersectionReasons: const [],
    ),
  );
}

class _TwoChannelFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _TwoChannelFeedMapNotifier(
    this.recommend,
    this.campus, [
    this._recommendObjectCards = const <FeedObjectCard>[],
  ]);

  final List<ContentPostViewData> recommend;
  final List<ContentPostViewData> campus;
  List<FeedObjectCard> _recommendObjectCards;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: recommend,
          objectCards: _recommendObjectCards,
        ),
      ),
      'campus': AsyncData(DiscoveryFeedState(items: campus)),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => const DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );

  void replaceRecommend(
    List<ContentPostViewData> items, {
    List<FeedObjectCard>? objectCards,
  }) {
    if (objectCards != null) {
      _recommendObjectCards = objectCards;
    }
    state = <String, AsyncValue<DiscoveryFeedState>>{
      ...state,
      'recommend': AsyncData(
        DiscoveryFeedState(items: items, objectCards: _recommendObjectCards),
      ),
    };
  }
}

class _NoopMediaDownloadCache extends MediaDownloadCache {
  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

final class _NoopPostInteractionStateNotifier
    extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<ContentPostViewData> posts) {}
}

final class _WidgetPagedDiscoveryFeedQuery
    implements ContentDiscoveryFeedQuery {
  int callCount = 0;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final pageIndex = cursor == null
        ? 0
        : int.parse(cursor.substring('cursor_'.length));
    callCount += 1;
    return DiscoveryFeedPage(
      items: List<ContentPostViewData>.generate(
        20,
        (index) => _post('resident_$pageIndex', index, bodyRepeats: 2),
      ),
      nextCursor: 'cursor_${pageIndex + 1}',
      feedRequestId: 'frq_widget_resident_$pageIndex',
      policyDigest:
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    );
  }
}

void main() {
  testWidgets(
    'top boundary restores a complete buffered page and preserves Post geometry',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final query = _WidgetPagedDiscoveryFeedQuery();
      final behaviorTracker = ContentBehaviorTracker(
        reporter: MockBehaviorRepository(),
        enablePeriodicFlush: false,
      );
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final anchorStore = HomeFeedScrollAnchorStore(maxChannels: 2);
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
          homeFeedScrollAnchorStoreProvider.overrideWithValue(anchorStore),
          contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(behaviorTracker.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);
      await notifier.load('recommend', force: true);
      for (var pageIndex = 1; pageIndex < 7; pageIndex += 1) {
        await notifier.appendNextPage('recommend');
      }
      expect(query.callCount, 7);
      expect(
        container
            .read(discoveryFeedMapProvider)['recommend']!
            .value!
            .items
            .first
            .id,
        'resident_3_anchor_post_0',
      );

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: CupertinoApp(
            home: ScreenUtilInit(
              designSize: const Size(390, 844),
              child: const MediaQuery(
                data: MediaQueryData(size: Size(390, 844)),
                child: HomeMultiFormFeed(
                  isDark: false,
                  channelId: 'recommend',
                  template: 'single_column_multiform',
                  onUserTap: _noopUserTap,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final scroll = find.byType(CustomScrollView);
      expect(scroll, findsOneWidget);
      expect(
        container
            .read(discoveryFeedMapProvider)['recommend']!
            .value!
            .items
            .first
            .id,
        'resident_3_anchor_post_0',
        reason:
            'mount/programmatic layout must not backslide without user intent',
      );

      await tester.drag(scroll, const Offset(0, -1800));
      await tester.pumpAndSettle();
      final deepOffset = tester
          .widget<CustomScrollView>(scroll)
          .controller!
          .offset;
      expect(deepOffset, greaterThan(844));

      await tester.drag(scroll, const Offset(0, 1600));
      await tester.pumpAndSettle();

      final backslid = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(backslid.items.first.id, 'resident_2_anchor_post_0');
      expect(backslid.hasBufferedNextPage, isTrue);
      expect(
        query.callCount,
        7,
        reason: 'backslide must use the retained page',
      );
      final saved = anchorStore.peek('recommend');
      expect(saved, isNotNull);
      expect(saved!.stableEntryIdentity, startsWith('post:resident_3_'));
      final restoredPost = find.byKey(
        ValueKey<String>(homeFeedEntryElementKey(saved.stableEntryIdentity)),
      );
      expect(restoredPost, findsOneWidget);
      final restoredViewportOffset =
          tester.getTopLeft(restoredPost).dy - tester.getTopLeft(scroll).dy;
      expect(restoredViewportOffset, closeTo(saved.viewportOffset, 1));

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    },
  );

  testWidgets(
    'channel restore keeps stable item viewport geometry after inserts shift it',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final recommend = List<ContentPostViewData>.generate(
        36,
        (index) => _post('recommend', index),
      );
      final campus = List<ContentPostViewData>.generate(
        20,
        (index) => _post('campus', index),
      );
      final activeChannel = ValueNotifier<String>('recommend');
      final anchorStore = HomeFeedScrollAnchorStore(maxChannels: 2);
      final feedNotifier = _TwoChannelFeedMapNotifier(recommend, campus);
      addTearDown(activeChannel.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            discoveryFeedMapProvider.overrideWith(() => feedNotifier),
            postInteractionStateProvider.overrideWith(
              _NoopPostInteractionStateNotifier.new,
            ),
            mediaDownloadCacheProvider.overrideWithValue(
              _NoopMediaDownloadCache(),
            ),
            homeFeedScrollAnchorStoreProvider.overrideWithValue(anchorStore),
          ],
          child: CupertinoApp(
            home: ScreenUtilInit(
              designSize: const Size(390, 844),
              child: MediaQuery(
                data: const MediaQueryData(size: Size(390, 844)),
                child: ValueListenableBuilder<String>(
                  valueListenable: activeChannel,
                  builder: (context, channelId, _) {
                    return HomeMultiFormFeed(
                      key: ValueKey<String>('test-feed-$channelId'),
                      isDark: false,
                      channelId: channelId,
                      template: 'single_column_multiform',
                      onUserTap:
                          (_, {avatarUrl, backgroundUrl, displayName}) {},
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -2200));
      await tester.pumpAndSettle();
      final before = tester
          .widget<CustomScrollView>(find.byType(CustomScrollView))
          .controller!
          .offset;
      expect(before, greaterThan(800));
      final mountedEntryKeys = tester
          .widgetList(
            find.byWidgetPredicate(
              (widget) =>
                  widget.key is ValueKey<String> &&
                  (widget.key! as ValueKey<String>).value.startsWith(
                    'home-feed-entry-',
                  ),
            ),
          )
          .map((widget) => (widget.key! as ValueKey<String>).value)
          .toList(growable: false);

      activeChannel.value = 'campus';
      await tester.pumpAndSettle();
      final saved = anchorStore.peek('recommend');
      expect(saved, isNotNull);
      expect(saved!.stableEntryIdentity, startsWith('post:recommend_'));
      expect(
        saved.entryIndex,
        greaterThan(0),
        reason:
            'identity=${saved.stableEntryIdentity} '
            'scroll=${saved.scrollOffset} viewport=${saved.viewportOffset} '
            'mounted=$mountedEntryKeys',
      );

      // 模拟频道离开期间刷新在锚点之前插入一批高度更大的内容。此时保存的
      // absolute scrollOffset 已无法挂载原锚点，恢复必须消费 entryIndex/当前
      // stable identity 索引做粗定位，再以真实 RenderObject geometry 校正。
      final refreshedRecommend = <ContentPostViewData>[
        ...List<ContentPostViewData>.generate(
          14,
          (index) => _post('refresh_insert', index, bodyRepeats: 6),
        ),
        ...recommend,
      ];
      feedNotifier.replaceRecommend(refreshedRecommend);
      await tester.pump();

      activeChannel.value = 'recommend';
      await tester.pumpAndSettle();
      final anchorFinder = find.byKey(
        ValueKey<String>(homeFeedEntryElementKey(saved.stableEntryIdentity)),
      );
      expect(anchorFinder, findsOneWidget);
      final restored = tester
          .widget<CustomScrollView>(find.byType(CustomScrollView))
          .controller!
          .offset;
      expect(
        (restored - before).abs(),
        greaterThan(500),
        reason: '新增内容后不能把旧 absolute offset 误判为锚点恢复成功',
      );
      final restoredViewportOffset =
          tester.getTopLeft(anchorFinder).dy -
          tester.getTopLeft(find.byType(CustomScrollView)).dy;
      expect(
        restoredViewportOffset,
        closeTo(saved.viewportOffset, 1),
        reason:
            'identity=${saved.stableEntryIdentity} '
            'savedViewport=${saved.viewportOffset} '
            'restoredViewport=$restoredViewportOffset '
            'savedIndex=${saved.entryIndex}',
      );

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    },
  );

  testWidgets(
    'volatile object card at viewport top saves and restores a Post anchor',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final recommend = List<ContentPostViewData>.generate(
        24,
        (index) => _post('object_anchor', index),
      );
      final campus = List<ContentPostViewData>.generate(
        12,
        (index) => _post('object_anchor_campus', index),
      );
      final objectCard = FeedObjectCard(
        objectKind: 'homepage',
        objectId: 'volatile-object-card',
        title: 'Volatile object card',
        tagRefs: const <String>[],
        anchorIndex: 8,
      );
      final activeChannel = ValueNotifier<String>('recommend');
      final anchorStore = HomeFeedScrollAnchorStore(maxChannels: 2);
      final feedNotifier = _TwoChannelFeedMapNotifier(
        recommend,
        campus,
        <FeedObjectCard>[objectCard],
      );
      addTearDown(activeChannel.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            discoveryFeedMapProvider.overrideWith(() => feedNotifier),
            postInteractionStateProvider.overrideWith(
              _NoopPostInteractionStateNotifier.new,
            ),
            mediaDownloadCacheProvider.overrideWithValue(
              _NoopMediaDownloadCache(),
            ),
            homeFeedScrollAnchorStoreProvider.overrideWithValue(anchorStore),
          ],
          child: CupertinoApp(
            home: ScreenUtilInit(
              designSize: const Size(390, 844),
              child: MediaQuery(
                data: const MediaQueryData(size: Size(390, 844)),
                child: ValueListenableBuilder<String>(
                  valueListenable: activeChannel,
                  builder: (context, channelId, _) => HomeMultiFormFeed(
                    key: ValueKey<String>('object-anchor-feed-$channelId'),
                    isDark: false,
                    channelId: channelId,
                    template: 'single_column_multiform',
                    onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      final objectFinder = find.byKey(
        const ValueKey<String>('home-object-card-volatile-object-card'),
      );
      await tester.scrollUntilVisible(
        objectFinder,
        500,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(objectFinder, findsOneWidget);
      await Scrollable.ensureVisible(
        tester.element(objectFinder),
        alignment: 0,
        duration: Duration.zero,
      );
      await tester.pumpAndSettle();
      expect(
        tester.getTopLeft(objectFinder).dy -
            tester.getTopLeft(find.byType(CustomScrollView)).dy,
        closeTo(0, 1),
      );

      activeChannel.value = 'campus';
      await tester.pumpAndSettle();
      final saved = anchorStore.peek('recommend');
      expect(saved, isNotNull);
      expect(
        saved!.stableEntryIdentity,
        startsWith('post:'),
        reason: 'refresh-volatile object cards must never be the only anchor',
      );

      feedNotifier.replaceRecommend(
        recommend,
        objectCards: const <FeedObjectCard>[],
      );
      await tester.pump();
      activeChannel.value = 'recommend';
      await tester.pumpAndSettle();

      expect(objectFinder, findsNothing);
      final restoredPost = find.byKey(
        ValueKey<String>(homeFeedEntryElementKey(saved.stableEntryIdentity)),
      );
      expect(restoredPost, findsOneWidget);
      final restoredViewportOffset =
          tester.getTopLeft(restoredPost).dy -
          tester.getTopLeft(find.byType(CustomScrollView)).dy;
      expect(restoredViewportOffset, closeTo(saved.viewportOffset, 1));

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    },
  );
}

void _noopUserTap(
  String userId, {
  String? avatarUrl,
  String? displayName,
  String? backgroundUrl,
}) {}
