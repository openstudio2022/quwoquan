// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/discovery_feed_resident_page_window.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy, ContentPostProjection, FeedObjectCard;

void main() {
  test('resident window keeps four visible pages and six retained pages', () {
    var window = DiscoveryFeedResidentPageWindow.initial(_page(0));

    for (var pageIndex = 1; pageIndex < 7; pageIndex += 1) {
      window = window.appendRemotePage(_page(pageIndex));
    }

    expect(window.residentPages, hasLength(homeFeedResidentPageLimit));
    expect(window.retainedPageCount, homeFeedRetainedPageLimit);
    expect(window.retainedItemCount, homeFeedRetainedPageLimit * 20);
    expect(window.visibleItems, hasLength(homeFeedResidentPageLimit * 20));
    expect(window.visibleItems.first.id, 'page_3_post_0');
    expect(window.visibleItems.last.id, 'page_6_post_19');
    expect(window.nextCursor, 'cursor_7');
    expect(window.canRestorePreviousPage, isTrue);
    expect(window.canRestoreNextPage, isFalse);
  });

  test(
    'backslide and forward restore move complete pages without cursor rewrite',
    () {
      var window = DiscoveryFeedResidentPageWindow.initial(_page(0));
      for (var pageIndex = 1; pageIndex < 7; pageIndex += 1) {
        window = window.appendRemotePage(_page(pageIndex));
      }

      final backslid = window.restorePreviousPage();
      expect(backslid, isNotNull);
      expect(backslid!.visibleItems.first.id, 'page_2_post_0');
      expect(backslid.nextCursor, 'cursor_6');
      expect(backslid.canRestoreNextPage, isTrue);

      final restored = backslid.restoreNextPage();
      expect(restored, isNotNull);
      expect(restored!.visibleItems.first.id, 'page_3_post_0');
      expect(restored.nextCursor, 'cursor_7');
      expect(restored.retainedPageCount, homeFeedRetainedPageLimit);
    },
  );

  test('remote prepend keeps four visible and six retained complete pages', () {
    var window = DiscoveryFeedResidentPageWindow.initial(_page(3));
    for (var pageIndex = 4; pageIndex < 7; pageIndex += 1) {
      window = window.appendRemotePage(_page(pageIndex));
    }

    expect(window.leadingPages, isEmpty);
    expect(window.previousCursor, 'previous_cursor_3');
    window = window.prependRemotePage(_page(2));

    expect(window.visibleItems.first.id, 'page_2_post_0');
    expect(window.visibleItems.last.id, 'page_5_post_19');
    expect(window.trailingPages.single.items.first.id, 'page_6_post_0');
    expect(window.residentPages, hasLength(homeFeedResidentPageLimit));
    expect(window.retainedPageCount, 5);
    expect(window.canRestoreNextPage, isTrue);
    expect(window.canRestorePreviousPage, isTrue);
  });

  test(
    'object-card anchors are rebased from page-local to visible-window index',
    () {
      var window = DiscoveryFeedResidentPageWindow.initial(_page(0));
      for (var pageIndex = 1; pageIndex < 5; pageIndex += 1) {
        window = window.appendRemotePage(_page(pageIndex));
      }

      expect(window.visibleObjectCards.map((card) => card.anchorIndex), <int>[
        1,
        21,
        41,
        61,
      ]);
      expect(window.visibleObjectCards.map((card) => card.objectId), <String>[
        'object_1',
        'object_2',
        'object_3',
        'object_4',
      ]);
    },
  );

  test('cross-page dedup rebases object-card anchors before window merge', () {
    final remoteItems = List.generate(4, (index) => _post(0, index));
    final page = DiscoveryFeedResidentPage.fromEnvelope(
      incomingCursor: 'cursor_1',
      page: DiscoveryFeedPage(
        items: remoteItems,
        objectCards: <FeedObjectCard>[
          FeedObjectCard(
            objectKind: 'homepage',
            objectId: 'object_after_duplicate',
            title: 'Object after duplicate',
            tagRefs: const <String>[],
            anchorIndex: 3,
          ),
        ],
        nextCursor: 'cursor_2',
      ),
      // 模拟第 1 项已在上一页出现：原 anchor=3 前只剩 2 个可见 Post。
      visibleItems: [remoteItems[0], remoteItems[2], remoteItems[3]],
    );

    expect(page.objectCards.single.anchorIndex, 2);
  });

  test(
    'remove and undo-insert rebase object-card anchors with the Post slot',
    () {
      final items = List.generate(4, (index) => _post(0, index));
      var window = DiscoveryFeedResidentPageWindow.initial(
        DiscoveryFeedResidentPage.fromEnvelope(
          incomingCursor: null,
          page: DiscoveryFeedPage(
            items: items,
            objectCards: <FeedObjectCard>[
              FeedObjectCard(
                objectKind: 'homepage',
                objectId: 'object_before_last',
                title: 'Object before last',
                tagRefs: const <String>[],
                anchorIndex: 3,
              ),
              FeedObjectCard(
                objectKind: 'homepage',
                objectId: 'object_after_page',
                title: 'Object after page',
                tagRefs: const <String>[],
                anchorIndex: 4,
              ),
            ],
            nextCursor: 'cursor_1',
          ),
        ),
      );

      window = window.removePost(items[1].id);
      expect(window.visibleObjectCards.map((card) => card.anchorIndex), <int>[
        2,
        3,
      ]);

      window = window.insertVisiblePost(index: 1, post: items[1]);
      expect(window.visibleObjectCards.map((card) => card.anchorIndex), <int>[
        3,
        4,
      ]);
    },
  );

  test(
    'undo restores the Post to its original resident page at a page boundary',
    () {
      var window = DiscoveryFeedResidentPageWindow.initial(_page(0));
      window = window.appendRemotePage(_page(1));
      final removedPost = window.residentPages[1].items.first;
      final placement = window.visiblePostPlacement(removedPost.id);

      expect(placement, isNotNull);
      window = window.removePost(removedPost.id);
      expect(window.residentPages.map((page) => page.items.length), <int>[
        20,
        19,
      ]);

      window = window.restoreVisiblePost(
        placement: placement!,
        post: removedPost,
      );

      expect(window.residentPages.map((page) => page.items.length), <int>[
        20,
        20,
      ]);
      expect(window.residentPages.first.items.last.id, 'page_0_post_19');
      expect(window.residentPages[1].items.first.id, 'page_1_post_0');
    },
  );

  test(
    'undo preserves an object-card anchor equal to the removed Post index',
    () {
      final items = List.generate(4, (index) => _post(0, index));
      var window = DiscoveryFeedResidentPageWindow.initial(
        DiscoveryFeedResidentPage.fromEnvelope(
          incomingCursor: null,
          page: DiscoveryFeedPage(
            items: items,
            objectCards: <FeedObjectCard>[
              FeedObjectCard(
                objectKind: 'homepage',
                objectId: 'object_before_removed',
                title: 'Object before removed',
                tagRefs: const <String>[],
                anchorIndex: 1,
              ),
              FeedObjectCard(
                objectKind: 'homepage',
                objectId: 'object_after_removed',
                title: 'Object after removed',
                tagRefs: const <String>[],
                anchorIndex: 3,
              ),
              FeedObjectCard(
                objectKind: 'homepage',
                objectId: 'object_after_page',
                title: 'Object after page',
                tagRefs: const <String>[],
                anchorIndex: 4,
              ),
            ],
            nextCursor: 'cursor_1',
          ),
        ),
      );
      final placement = window.visiblePostPlacement(items[1].id);

      expect(placement, isNotNull);
      window = window.removePost(items[1].id);
      expect(window.visibleObjectCards.map((card) => card.anchorIndex), <int>[
        1,
        2,
        3,
      ]);

      window = window.restoreVisiblePost(placement: placement!, post: items[1]);

      expect(window.visibleObjectCards.map((card) => card.anchorIndex), <int>[
        1,
        3,
        4,
      ]);
      expect(
        window.visibleItems.map((post) => post.id),
        items.map((post) => post.id),
      );
    },
  );

  test('a remote page over the request budget fails closed', () {
    final remoteItems = List.generate(21, (index) => _post(0, index));
    expect(
      () => DiscoveryFeedResidentPage.fromEnvelope(
        incomingCursor: null,
        page: DiscoveryFeedPage(
          items: remoteItems,
          nextCursor: 'cursor_1',
          feedRequestId: 'frq_oversized',
        ),
        visibleItems: remoteItems.take(20).toList(growable: false),
      ),
      throwsA(
        isA<DiscoveryFeedPageBudgetExceeded>()
            .having((error) => error.actualItems, 'actualItems', 21)
            .having((error) => error.maximumItems, 'maximumItems', 20),
      ),
    );
  });
}

DiscoveryFeedResidentPage _page(int pageIndex) {
  return DiscoveryFeedResidentPage.fromEnvelope(
    incomingCursor: pageIndex == 0 ? null : 'cursor_$pageIndex',
    page: DiscoveryFeedPage(
      items: List.generate(20, (index) => _post(pageIndex, index)),
      objectCards: <FeedObjectCard>[
        FeedObjectCard(
          objectKind: 'homepage',
          objectId: 'object_$pageIndex',
          title: 'Object $pageIndex',
          tagRefs: const <String>[],
          anchorIndex: 1,
        ),
      ],
      nextCursor: 'cursor_${pageIndex + 1}',
      previousCursor: pageIndex == 0 ? null : 'previous_cursor_$pageIndex',
      paginationExpiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)),
      feedRequestId: 'frq_window_test',
    ),
  );
}

ContentPostViewData _post(int pageIndex, int itemIndex) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'page_${pageIndex}_post_$itemIndex',
      contentType: 'micro',
      contentIdentity: 'moment',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author_$pageIndex',
      authorDisplayName: 'Window Author',
      authorAvatarUrl: '',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: 'bounded resident window item',
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 7, 29),
    ),
  );
}
