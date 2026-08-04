import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/domain/discovery_feed_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show FeedObjectCard;

/// 首页固定以 20 条请求一页；响应超过请求预算时必须 fail-closed，不能截断后
/// 跳过同一 opaque continuation 中的内容。
const int homeFeedPageItemLimit = 20;

/// 可见列表最多保留四个完整远端页；另外两个页槽在前后方向间动态流转，
/// 因而总 Post 引用上限为 6 * 20 = 120。
const int homeFeedResidentPageLimit = 4;
const int homeFeedRetainedPageLimit = 6;
const int homeFeedSeenItemLimit = 2048;

final class DiscoveryFeedPageBudgetExceeded implements Exception {
  const DiscoveryFeedPageBudgetExceeded({
    required this.actualItems,
    required this.maximumItems,
  });

  final int actualItems;
  final int maximumItems;

  @override
  String toString() {
    return 'DiscoveryFeedPageBudgetExceeded('
        'actualItems: $actualItems, maximumItems: $maximumItems)';
  }
}

@immutable
final class DiscoveryFeedResidentPage {
  DiscoveryFeedResidentPage({
    required this.incomingCursor,
    required List<ContentPostViewData> items,
    required this.nextCursor,
    this.previousCursor,
    this.paginationExpiresAt,
    List<FeedObjectCard> objectCards = const <FeedObjectCard>[],
    int maxItems = homeFeedPageItemLimit,
  }) : items = List<ContentPostViewData>.unmodifiable(items),
       objectCards = List<FeedObjectCard>.unmodifiable(objectCards) {
    if (items.length > maxItems) {
      throw DiscoveryFeedPageBudgetExceeded(
        actualItems: items.length,
        maximumItems: maxItems,
      );
    }
  }

  factory DiscoveryFeedResidentPage.fromEnvelope({
    required String? incomingCursor,
    required DiscoveryFeedPage page,
    List<ContentPostViewData>? visibleItems,
    int maxItems = homeFeedPageItemLimit,
  }) {
    // 预算约束针对 Remote envelope，而不是去重后的展示投影。否则 21 条响应
    // 只要包含一条重复 Post 就可能在去重后伪装成合法 20 条，破坏 cursor 页界。
    if (page.items.length > maxItems) {
      throw DiscoveryFeedPageBudgetExceeded(
        actualItems: page.items.length,
        maximumItems: maxItems,
      );
    }
    final resolvedVisibleItems = visibleItems ?? page.items;
    return DiscoveryFeedResidentPage(
      incomingCursor: _normalizedCursor(incomingCursor),
      items: resolvedVisibleItems,
      nextCursor: _normalizedCursor(page.nextCursor),
      previousCursor: _normalizedCursor(page.previousCursor),
      paginationExpiresAt: page.paginationExpiresAt,
      objectCards: _rebasePageObjectCardsAfterDeduplication(
        remoteItems: page.items,
        visibleItems: resolvedVisibleItems,
        objectCards: page.objectCards,
      ),
      maxItems: maxItems,
    );
  }

  final String? incomingCursor;
  final List<ContentPostViewData> items;
  final String? nextCursor;
  final String? previousCursor;
  final DateTime? paginationExpiresAt;
  final List<FeedObjectCard> objectCards;

  DiscoveryFeedResidentPage withPreviousCursor(String? cursor) {
    return DiscoveryFeedResidentPage(
      incomingCursor: incomingCursor,
      items: items,
      nextCursor: nextCursor,
      previousCursor: _normalizedCursor(cursor),
      paginationExpiresAt: paginationExpiresAt,
      objectCards: objectCards,
    );
  }

  DiscoveryFeedResidentPage withoutPost(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return this;
    }
    final nextItems = items
        .where((item) => item.id != normalized)
        .toList(growable: false);
    if (nextItems.length == items.length) {
      return this;
    }
    return DiscoveryFeedResidentPage(
      incomingCursor: incomingCursor,
      items: nextItems,
      nextCursor: nextCursor,
      previousCursor: previousCursor,
      paginationExpiresAt: paginationExpiresAt,
      objectCards: _rebasePageObjectCardsAfterDeduplication(
        remoteItems: items,
        visibleItems: nextItems,
        objectCards: objectCards,
      ),
    );
  }

  DiscoveryFeedResidentPage insertPost({
    required int index,
    required ContentPostViewData post,
  }) {
    final insertionIndex = index.clamp(0, items.length);
    final nextItems = items.toList(growable: true)
      ..insert(insertionIndex, post);
    final nextObjectCards = objectCards
        .map((card) {
          final anchorIndex = card.anchorIndex.clamp(0, items.length);
          return _feedObjectCardAt(
            card,
            anchorIndex: anchorIndex >= insertionIndex
                ? anchorIndex + 1
                : anchorIndex,
          );
        })
        .toList(growable: false);
    return DiscoveryFeedResidentPage(
      incomingCursor: incomingCursor,
      items: nextItems,
      nextCursor: nextCursor,
      previousCursor: previousCursor,
      paginationExpiresAt: paginationExpiresAt,
      objectCards: nextObjectCards,
    );
  }
}

/// 本地乐观删除前的页内位置事实。
///
/// 撤销不能只依赖展开列表中的全局索引：页边界索引同时可表示上一页末尾和
/// 下一页开头。对象卡 anchor 在删除点两侧也会折叠为同一数值，因此同时保留
/// 原页游标身份、resident 位置和删除前的页内锚点。
@immutable
final class DiscoveryFeedVisiblePostPlacement {
  DiscoveryFeedVisiblePostPlacement({
    required this.postId,
    required this.residentPageIndex,
    required this.pageItemIndex,
    required this.pageIncomingCursor,
    required this.pageNextCursor,
    required List<int> objectCardAnchorIndices,
  }) : objectCardAnchorIndices = List<int>.unmodifiable(
         objectCardAnchorIndices,
       );

  final String postId;
  final int residentPageIndex;
  final int pageItemIndex;
  final String? pageIncomingCursor;
  final String? pageNextCursor;
  final List<int> objectCardAnchorIndices;

  bool identifies(DiscoveryFeedResidentPage page) {
    return page.incomingCursor == pageIncomingCursor &&
        page.nextCursor == pageNextCursor;
  }
}

/// 按远端响应页边界维护的首页内存窗口。
///
/// [residentPages] 是当前 Widget 真正展开的页；[leadingPages] 与
/// [trailingPages] 是同一有界窗口内可立即回补的一页级 backslide/forward
/// 缓冲。三者合计不超过 [maxRetainedPages]，移动只发生在完整页边界，绝不
/// 解析或改写 opaque cursor。
@immutable
final class DiscoveryFeedResidentPageWindow {
  DiscoveryFeedResidentPageWindow._({
    required List<DiscoveryFeedResidentPage> leadingPages,
    required List<DiscoveryFeedResidentPage> residentPages,
    required List<DiscoveryFeedResidentPage> trailingPages,
    required this.maxResidentPages,
    required this.maxRetainedPages,
  }) : leadingPages = List<DiscoveryFeedResidentPage>.unmodifiable(
         leadingPages,
       ),
       residentPages = List<DiscoveryFeedResidentPage>.unmodifiable(
         residentPages,
       ),
       trailingPages = List<DiscoveryFeedResidentPage>.unmodifiable(
         trailingPages,
       ) {
    assert(maxResidentPages > 0);
    assert(maxRetainedPages >= maxResidentPages);
    assert(residentPages.length <= maxResidentPages);
    assert(
      leadingPages.length + residentPages.length + trailingPages.length <=
          maxRetainedPages,
    );
  }

  factory DiscoveryFeedResidentPageWindow.initial(
    DiscoveryFeedResidentPage page, {
    int maxResidentPages = homeFeedResidentPageLimit,
    int maxRetainedPages = homeFeedRetainedPageLimit,
  }) {
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: const <DiscoveryFeedResidentPage>[],
      residentPages: <DiscoveryFeedResidentPage>[page],
      trailingPages: const <DiscoveryFeedResidentPage>[],
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  final List<DiscoveryFeedResidentPage> leadingPages;
  final List<DiscoveryFeedResidentPage> residentPages;
  final List<DiscoveryFeedResidentPage> trailingPages;
  final int maxResidentPages;
  final int maxRetainedPages;

  bool get canRestorePreviousPage =>
      leadingPages.isNotEmpty || (previousCursor?.isNotEmpty ?? false);
  bool get canRestoreNextPage => trailingPages.isNotEmpty;
  int get retainedPageCount =>
      leadingPages.length + residentPages.length + trailingPages.length;
  int get retainedItemCount =>
      _allPages.fold<int>(0, (count, page) => count + page.items.length);
  String? get nextCursor {
    if (residentPages.isEmpty) {
      return null;
    }
    final last = residentPages.last;
    final expiresAt = last.paginationExpiresAt;
    if (expiresAt != null && !expiresAt.isAfter(DateTime.now().toUtc())) {
      return null;
    }
    return last.nextCursor;
  }

  String? get previousCursor {
    if (residentPages.isEmpty) {
      return null;
    }
    final first = residentPages.first;
    final expiresAt = first.paginationExpiresAt;
    if (expiresAt == null || !expiresAt.isAfter(DateTime.now().toUtc())) {
      return null;
    }
    return first.previousCursor;
  }

  Iterable<DiscoveryFeedResidentPage> get _allPages sync* {
    yield* leadingPages;
    yield* residentPages;
    yield* trailingPages;
  }

  List<ContentPostViewData> get visibleItems =>
      List<ContentPostViewData>.unmodifiable(
        residentPages.expand((page) => page.items),
      );

  List<FeedObjectCard> get visibleObjectCards {
    final cards = <FeedObjectCard>[];
    var precedingItems = 0;
    for (final page in residentPages) {
      for (final card in page.objectCards) {
        cards.add(
          _feedObjectCardAt(
            card,
            anchorIndex:
                precedingItems + card.anchorIndex.clamp(0, page.items.length),
          ),
        );
      }
      precedingItems += page.items.length;
    }
    return List<FeedObjectCard>.unmodifiable(cards);
  }

  Set<String> get retainedPostIds => _allPages
      .expand((page) => page.items)
      .map((post) => post.id.trim())
      .where((postId) => postId.isNotEmpty)
      .toSet();

  DiscoveryFeedResidentPageWindow appendRemotePage(
    DiscoveryFeedResidentPage page,
  ) {
    if (trailingPages.isNotEmpty) {
      throw StateError(
        'buffered trailing pages must be restored before remote append',
      );
    }
    final leading = leadingPages.toList(growable: true);
    final resident = residentPages.toList(growable: true)..add(page);
    while (resident.length > maxResidentPages) {
      leading.add(resident.removeAt(0));
    }
    while (leading.length + resident.length > maxRetainedPages) {
      leading.removeAt(0);
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leading,
      residentPages: resident,
      trailingPages: const <DiscoveryFeedResidentPage>[],
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedResidentPageWindow prependRemotePage(
    DiscoveryFeedResidentPage page,
  ) {
    if (leadingPages.isNotEmpty) {
      throw StateError(
        'buffered leading pages must be restored before remote prepend',
      );
    }
    final resident = residentPages.toList(growable: true)..insert(0, page);
    final trailing = trailingPages.toList(growable: true);
    while (resident.length > maxResidentPages) {
      trailing.insert(0, resident.removeLast());
    }
    while (resident.length + trailing.length > maxRetainedPages) {
      trailing.removeLast();
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: const <DiscoveryFeedResidentPage>[],
      residentPages: resident,
      trailingPages: trailing,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  /// Advances the opaque remote backslide boundary without retaining an empty
  /// page. A delivered page can legitimately shrink to zero after current
  /// visibility hydration; keeping an empty resident page would evict visible
  /// content and distort the four-page window.
  DiscoveryFeedResidentPageWindow withRemotePreviousCursor(String? cursor) {
    if (residentPages.isEmpty) {
      return this;
    }
    final resident = residentPages.toList(growable: true);
    resident[0] = resident[0].withPreviousCursor(cursor);
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leadingPages,
      residentPages: resident,
      trailingPages: trailingPages,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedResidentPageWindow? restorePreviousPage() {
    if (leadingPages.isEmpty || residentPages.isEmpty) {
      return null;
    }
    final leading = leadingPages.toList(growable: true);
    final resident = residentPages.toList(growable: true);
    final trailing = trailingPages.toList(growable: true);
    resident.insert(0, leading.removeLast());
    if (resident.length > maxResidentPages) {
      trailing.insert(0, resident.removeLast());
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leading,
      residentPages: resident,
      trailingPages: trailing,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedResidentPageWindow? restoreNextPage() {
    if (trailingPages.isEmpty || residentPages.isEmpty) {
      return null;
    }
    final leading = leadingPages.toList(growable: true);
    final resident = residentPages.toList(growable: true);
    final trailing = trailingPages.toList(growable: true);
    resident.add(trailing.removeAt(0));
    if (resident.length > maxResidentPages) {
      leading.add(resident.removeAt(0));
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leading,
      residentPages: resident,
      trailingPages: trailing,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedResidentPageWindow removePost(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return this;
    }
    List<DiscoveryFeedResidentPage> removeFrom(
      List<DiscoveryFeedResidentPage> pages,
    ) {
      return pages
          .map((page) => page.withoutPost(normalized))
          .toList(growable: false);
    }

    return DiscoveryFeedResidentPageWindow._(
      leadingPages: removeFrom(leadingPages),
      residentPages: removeFrom(residentPages),
      trailingPages: removeFrom(trailingPages),
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedVisiblePostPlacement? visiblePostPlacement(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return null;
    }
    for (
      var residentPageIndex = 0;
      residentPageIndex < residentPages.length;
      residentPageIndex += 1
    ) {
      final page = residentPages[residentPageIndex];
      final pageItemIndex = page.items.indexWhere(
        (item) => item.id == normalized,
      );
      if (pageItemIndex < 0) {
        continue;
      }
      return DiscoveryFeedVisiblePostPlacement(
        postId: normalized,
        residentPageIndex: residentPageIndex,
        pageItemIndex: pageItemIndex,
        pageIncomingCursor: page.incomingCursor,
        pageNextCursor: page.nextCursor,
        objectCardAnchorIndices: page.objectCards
            .map((card) => card.anchorIndex)
            .toList(growable: false),
      );
    }
    return null;
  }

  DiscoveryFeedResidentPageWindow restoreVisiblePost({
    required DiscoveryFeedVisiblePostPlacement placement,
    required ContentPostViewData post,
  }) {
    final normalizedPostId = post.id.trim();
    if (normalizedPostId.isEmpty ||
        normalizedPostId != placement.postId ||
        retainedPostIds.contains(normalizedPostId)) {
      return this;
    }

    DiscoveryFeedResidentPage? restoredPage(DiscoveryFeedResidentPage page) {
      if (!placement.identifies(page) ||
          page.items.length >= homeFeedPageItemLimit ||
          page.objectCards.length != placement.objectCardAnchorIndices.length) {
        return null;
      }
      final insertionIndex = placement.pageItemIndex.clamp(
        0,
        page.items.length,
      );
      final nextItems = page.items.toList(growable: true)
        ..insert(insertionIndex, post);
      final nextObjectCards = <FeedObjectCard>[];
      for (var index = 0; index < page.objectCards.length; index += 1) {
        final card = page.objectCards[index];
        final originalAnchor = placement.objectCardAnchorIndices[index].clamp(
          0,
          nextItems.length,
        );
        nextObjectCards.add(
          _feedObjectCardAt(
            card,
            anchorIndex: originalAnchor > placement.pageItemIndex
                ? (card.anchorIndex + 1).clamp(0, nextItems.length)
                : card.anchorIndex.clamp(0, nextItems.length),
          ),
        );
      }
      return DiscoveryFeedResidentPage(
        incomingCursor: page.incomingCursor,
        items: nextItems,
        nextCursor: page.nextCursor,
        objectCards: nextObjectCards,
      );
    }

    ({List<DiscoveryFeedResidentPage> pages, bool restored}) restoreIn(
      List<DiscoveryFeedResidentPage> source, {
      int? preferredIndex,
    }) {
      final indices = <int>[
        if (preferredIndex != null &&
            preferredIndex >= 0 &&
            preferredIndex < source.length)
          preferredIndex,
        for (var index = 0; index < source.length; index += 1)
          if (index != preferredIndex) index,
      ];
      for (final index in indices) {
        final restored = restoredPage(source[index]);
        if (restored == null) {
          continue;
        }
        final pages = source.toList(growable: true);
        pages[index] = restored;
        return (pages: pages, restored: true);
      }
      return (pages: source, restored: false);
    }

    final resident = restoreIn(
      residentPages,
      preferredIndex: placement.residentPageIndex,
    );
    if (resident.restored) {
      return DiscoveryFeedResidentPageWindow._(
        leadingPages: leadingPages,
        residentPages: resident.pages,
        trailingPages: trailingPages,
        maxResidentPages: maxResidentPages,
        maxRetainedPages: maxRetainedPages,
      );
    }
    final leading = restoreIn(leadingPages);
    if (leading.restored) {
      return DiscoveryFeedResidentPageWindow._(
        leadingPages: leading.pages,
        residentPages: residentPages,
        trailingPages: trailingPages,
        maxResidentPages: maxResidentPages,
        maxRetainedPages: maxRetainedPages,
      );
    }
    final trailing = restoreIn(trailingPages);
    if (!trailing.restored) {
      return this;
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leadingPages,
      residentPages: residentPages,
      trailingPages: trailing.pages,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }

  DiscoveryFeedResidentPageWindow insertVisiblePost({
    required int index,
    required ContentPostViewData post,
  }) {
    if (residentPages.isEmpty || retainedPostIds.contains(post.id)) {
      return this;
    }
    final resident = residentPages.toList(growable: true);
    var remaining = index.clamp(0, visibleItems.length);
    for (var pageIndex = 0; pageIndex < resident.length; pageIndex += 1) {
      final page = resident[pageIndex];
      if (remaining <= page.items.length || pageIndex == resident.length - 1) {
        resident[pageIndex] = page.insertPost(index: remaining, post: post);
        break;
      }
      remaining -= page.items.length;
    }
    return DiscoveryFeedResidentPageWindow._(
      leadingPages: leadingPages,
      residentPages: resident,
      trailingPages: trailingPages,
      maxResidentPages: maxResidentPages,
      maxRetainedPages: maxRetainedPages,
    );
  }
}

String? _normalizedCursor(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

List<FeedObjectCard> _rebasePageObjectCardsAfterDeduplication({
  required List<ContentPostViewData> remoteItems,
  required List<ContentPostViewData> visibleItems,
  required List<FeedObjectCard> objectCards,
}) {
  if (objectCards.isEmpty || identical(remoteItems, visibleItems)) {
    return objectCards;
  }

  // visibleItems 是 remoteItems 的保序子序列。对象卡的 anchorIndex 基于原始
  // envelope；跨页去重删除前序 Post 后，必须把它重映射为“原 anchor 前仍可见
  // 的 Post 数”。只 clamp 会让卡片漂移到错误内容之后。
  final visiblePrefixCounts = List<int>.filled(remoteItems.length + 1, 0);
  var visibleIndex = 0;
  for (
    var remoteIndex = 0;
    remoteIndex < remoteItems.length;
    remoteIndex += 1
  ) {
    if (visibleIndex < visibleItems.length &&
        remoteItems[remoteIndex].id == visibleItems[visibleIndex].id) {
      visibleIndex += 1;
    }
    visiblePrefixCounts[remoteIndex + 1] = visibleIndex;
  }
  return objectCards
      .map(
        (card) => _feedObjectCardAt(
          card,
          anchorIndex:
              visiblePrefixCounts[card.anchorIndex.clamp(
                0,
                remoteItems.length,
              )],
        ),
      )
      .toList(growable: false);
}

FeedObjectCard _feedObjectCardAt(
  FeedObjectCard source, {
  required int anchorIndex,
}) => FeedObjectCard(
  objectKind: source.objectKind,
  objectId: source.objectId,
  title: source.title,
  subtitle: source.subtitle,
  coverUrl: source.coverUrl,
  tagRefs: source.tagRefs,
  reasonText: source.reasonText,
  recallPath: source.recallPath,
  anchorIndex: anchorIndex,
);
