// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

const String _policyA =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const String _policyB =
    'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  test(
    'provider trims at page boundaries and restores buffered pages locally',
    () async {
      final query = _PagedDiscoveryFeedQuery();
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      for (var pageIndex = 1; pageIndex < 7; pageIndex += 1) {
        await notifier.appendNextPage('recommend');
      }

      final afterAppend = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(query.callCount, 7);
      expect(afterAppend.items, hasLength(80));
      expect(afterAppend.items.first.id, 'page_3_post_0');
      expect(afterAppend.items.last.id, 'page_6_post_19');
      expect(afterAppend.seenItemIds, hasLength(140));
      expect(afterAppend.residentPageCount, 4);
      expect(afterAppend.retainedPageCount, 6);
      expect(afterAppend.canRestorePreviousPage, isTrue);
      expect(afterAppend.hasBufferedNextPage, isFalse);
      expect(afterAppend.policyDigest, _policyA);
      expect(notifier.residentPageWindowDiagnostics('recommend'), (
        leadingPages: 2,
        residentPages: 4,
        trailingPages: 0,
        retainedPages: 6,
        retainedItems: 120,
      ));

      expect(notifier.restorePreviousPage('recommend'), isTrue);
      final backslid = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(backslid.items.first.id, 'page_2_post_0');
      expect(backslid.hasBufferedNextPage, isTrue);

      await notifier.appendNextPage('recommend');
      final restored = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(
        query.callCount,
        7,
        reason: 'buffered forward restore must not issue Remote I/O',
      );
      expect(restored.items.first.id, 'page_3_post_0');
      expect(restored.nextCursor, 'cursor_7');
    },
  );

  test(
    'expired resident cursor is cleared without issuing remote continuation',
    () async {
      final query = _PagedDiscoveryFeedQuery(
        firstPageExpiry: const Duration(milliseconds: 500),
      );
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      final loaded = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(loaded.nextCursor, 'cursor_1');

      // No provider rebuild occurs while the page is idle. The render snapshot
      // therefore still contains the cursor when the server expiry passes.
      await Future<void>.delayed(const Duration(milliseconds: 650));

      await notifier.appendNextPage('recommend');

      final expired = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(query.callCount, 1);
      expect(expired.nextCursor, isNull);
      expect(expired.hasMore, isFalse);
      expect(expired.appendError, isNull);
    },
  );

  test(
    'provider uses remote previous cursor after bounded local history is exhausted',
    () async {
      final query = _PagedDiscoveryFeedQuery();
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      for (var pageIndex = 1; pageIndex < 7; pageIndex += 1) {
        await notifier.appendNextPage('recommend');
      }
      expect(await notifier.prependPreviousPage('recommend'), isTrue);
      expect(await notifier.prependPreviousPage('recommend'), isTrue);
      expect(query.callCount, 7, reason: 'two retained pages restore locally');

      expect(await notifier.prependPreviousPage('recommend'), isTrue);
      final restored = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(query.callCount, 8);
      expect(restored.items.first.id, 'page_0_post_0');
      expect(
        restored.seenItemIds,
        contains('page_0_post_0'),
        reason: 'historical seen state cannot suppress an evicted stable page',
      );
      expect(restored.isPrepending, isFalse);
      expect(restored.prependError, isNull);
      expect(restored.residentPageCount, 4);
      expect(restored.retainedPageCount, 6);
    },
  );

  test(
    'oversized remote continuation fails closed before attribution side effects',
    () async {
      final query = _PagedDiscoveryFeedQuery(oversizedPageIndex: 1);
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      expect(
        container.read(feedSessionProvider.notifier).currentFeedRequestId,
        'frq_resident_window',
      );

      await notifier.appendNextPage('recommend');

      final failed = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(query.callCount, 2);
      expect(failed.items, hasLength(20));
      expect(failed.items.first.id, 'page_0_post_0');
      expect(failed.seenItemIds, hasLength(20));
      expect(failed.residentPageCount, 1);
      expect(failed.retainedPageCount, 1);
      expect(failed.appendError, isNotNull);
      expect(
        container.read(feedSessionProvider.notifier).currentFeedRequestId,
        'frq_resident_window',
        reason: 'rejected envelope must not replace the accepted attribution',
      );
    },
  );

  test('continuation policyDigest 改变时 fail-closed 且不污染已接纳窗口', () async {
    final query = _PagedDiscoveryFeedQuery(mismatchedPolicyPageIndex: 1);
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final container = ProviderContainer(
      overrides: [
        contentDiscoveryFeedQueryProvider.overrideWithValue(query),
        homeChannelsProvider.overrideWithValue([recommend]),
        postInteractionStateProvider.overrideWith(
          _NoopPostInteractionStateNotifier.new,
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(discoveryFeedMapProvider.notifier);

    await notifier.load('recommend', force: true);
    await notifier.appendNextPage('recommend');

    final failed = container
        .read(discoveryFeedMapProvider)['recommend']!
        .value!;
    expect(query.callCount, 2);
    expect(failed.items, hasLength(20));
    expect(failed.items.first.id, 'page_0_post_0');
    expect(failed.policyDigest, _policyA);
    expect(failed.appendError, isNotNull);
  });

  test(
    'initial provider boundary rejects a non-canonical policyDigest',
    () async {
      final query = _PagedDiscoveryFeedQuery(invalidPolicyPageIndex: 0);
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);

      await container
          .read(discoveryFeedMapProvider.notifier)
          .load('recommend', force: true);

      final failed = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(failed.items, isEmpty);
      expect(failed.policyDigest, isNull);
      expect(failed.blockingError, isNotNull);
    },
  );

  test(
    'concurrent channels retain independent policyDigest identities',
    () async {
      final query = _ChannelPolicyDiscoveryFeedQuery();
      final channels = ContentUIConfig.homeChannels
          .where(
            (channel) => channel.id == 'recommend' || channel.id == 'campus',
          )
          .toList(growable: false);
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue(channels),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      await notifier.load('campus', force: true);

      final feedMap = container.read(discoveryFeedMapProvider);
      expect(feedMap['recommend']!.value!.policyDigest, _policyA);
      expect(feedMap['recommend']!.value!.feedRequestId, 'frq_recommend');
      expect(feedMap['campus']!.value!.policyDigest, _policyB);
      expect(feedMap['campus']!.value!.feedRequestId, 'frq_campus');
    },
  );

  test(
    'provider undo retains the original resident page and equal object-card anchor',
    () async {
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(
            _PagedDiscoveryFeedQuery(),
          ),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      await notifier.appendNextPage('recommend');
      final before = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(before.items, hasLength(40));
      expect(before.objectCards.single.anchorIndex, 20);

      final removed = notifier.removePostLocally('page_1_post_0');
      final during = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(during.items, hasLength(39));
      expect(during.objectCards.single.anchorIndex, 20);

      notifier.restorePostsLocally(removed);
      final restored = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(restored.items, hasLength(40));
      expect(restored.items[19].id, 'page_0_post_19');
      expect(restored.items[20].id, 'page_1_post_0');
      expect(restored.objectCards.single.anchorIndex, 20);
    },
  );

  test(
    'provider crosses the six-page boundary with previous cursor and can revisit an evicted forward page',
    () async {
      final query = _BidirectionalPagedDiscoveryFeedQuery();
      final recommend = ContentUIConfig.homeChannels.firstWhere(
        (channel) => channel.id == 'recommend',
      );
      final container = ProviderContainer(
        overrides: [
          contentDiscoveryFeedQueryProvider.overrideWithValue(query),
          homeChannelsProvider.overrideWithValue([recommend]),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ],
      );
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend', force: true);
      for (var pageIndex = 1; pageIndex < 8; pageIndex += 1) {
        await notifier.appendNextPage('recommend');
      }
      expect(query.callCount, 8);
      expect(notifier.restorePreviousPage('recommend'), isTrue);
      expect(notifier.restorePreviousPage('recommend'), isTrue);

      final restoredRemotely = await notifier.prependPreviousPage('recommend');
      final previous = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(restoredRemotely, isTrue);
      expect(query.callCount, 9);
      expect(previous.items.first.id, 'page_1_post_0');
      expect(previous.items.last.id, 'page_4_post_19');
      expect(previous.canRestorePreviousPage, isTrue);

      // Pages 5 and 6 are still buffered. Page 7 was already seen but was
      // evicted while moving the bounded window backward; reloading it through the original
      // outbound cursor must not be erased by the historical seen LRU.
      await notifier.appendNextPage('recommend');
      expect(query.callCount, 9);
      await notifier.appendNextPage('recommend');
      expect(query.callCount, 9);
      await notifier.appendNextPage('recommend');
      final revisited = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(query.callCount, 10);
      expect(revisited.items.last.id, 'page_7_post_19');
      expect(revisited.items, hasLength(80));
    },
  );
}

final class _NoopPostInteractionStateNotifier
    extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<PostBaseDto> posts) {}
}

final class _PagedDiscoveryFeedQuery implements ContentDiscoveryFeedQuery {
  _PagedDiscoveryFeedQuery({
    this.oversizedPageIndex,
    this.mismatchedPolicyPageIndex,
    this.invalidPolicyPageIndex,
    this.firstPageExpiry = const Duration(minutes: 10),
  });

  final int? oversizedPageIndex;
  final int? mismatchedPolicyPageIndex;
  final int? invalidPolicyPageIndex;
  final Duration firstPageExpiry;
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
        : int.parse(
            cursor.substring(
              cursor.startsWith('previous_')
                  ? 'previous_'.length
                  : 'cursor_'.length,
            ),
          );
    callCount += 1;
    return DiscoveryFeedPage(
      items: List.generate(
        pageIndex == oversizedPageIndex ? 21 : 20,
        (index) => _post(pageIndex, index),
      ),
      objectCards: pageIndex == 1
          ? <FeedObjectCardDto>[
              FeedObjectCardDto(
                objectKind: 'homepage',
                objectId: 'object_before_page_1',
                title: 'Object before page 1',
                anchorIndex: 0,
              ),
            ]
          : const <FeedObjectCardDto>[],
      nextCursor: 'cursor_${pageIndex + 1}',
      previousCursor: pageIndex == 0 ? null : 'previous_${pageIndex - 1}',
      paginationExpiresAt: DateTime.now().toUtc().add(
        pageIndex == 0 ? firstPageExpiry : const Duration(minutes: 10),
      ),
      feedRequestId: 'frq_resident_window',
      policyDigest: pageIndex == invalidPolicyPageIndex
          ? ' $_policyA'
          : pageIndex == mismatchedPolicyPageIndex
          ? _policyB
          : _policyA,
    );
  }
}

final class _BidirectionalPagedDiscoveryFeedQuery
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
    final pageIndex = switch (cursor) {
      null => 0,
      final value when value.startsWith('next_') => int.parse(
        value.substring('next_'.length),
      ),
      final value when value.startsWith('previous_') => int.parse(
        value.substring('previous_'.length),
      ),
      _ => throw FormatException('unexpected test cursor: $cursor'),
    };
    callCount += 1;
    return DiscoveryFeedPage(
      items: List.generate(20, (index) => _post(pageIndex, index)),
      nextCursor: 'next_${pageIndex + 1}',
      previousCursor: pageIndex == 0 ? null : 'previous_${pageIndex - 1}',
      paginationExpiresAt: DateTime.now().add(const Duration(minutes: 10)),
      feedRequestId: 'frq_bidirectional_window',
      policyDigest: _policyA,
    );
  }
}

final class _ChannelPolicyDiscoveryFeedQuery
    implements ContentDiscoveryFeedQuery {
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
    final channel = channelId ?? category;
    final isRecommend = channel == 'recommend';
    return DiscoveryFeedPage(
      items: <PostBaseDto>[_post(isRecommend ? 10 : 20, 0)],
      feedRequestId: 'frq_$channel',
      policyDigest: isRecommend ? _policyA : _policyB,
    );
  }
}

MicroPostDto _post(int pageIndex, int itemIndex) {
  return MicroPostDto(
    id: 'page_${pageIndex}_post_$itemIndex',
    type: 'moment',
    identity: 'moment',
    assistantUsePolicy: 'allow',
    authorId: 'author_$pageIndex',
    displayName: 'Window Author',
    avatarUrl: '',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: 'provider resident page item',
    imageUrls: const <String>[],
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.utc(2026, 7, 29),
  );
}
