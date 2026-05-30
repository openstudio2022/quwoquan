import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';

/// 单类 feed 状态：items + nextCursor
class DiscoveryFeedState {
  static const Object _unset = Object();

  const DiscoveryFeedState({
    this.items = const [],
    this.seenItemIds = const [],
    this.nextCursor,
    this.isLoading = false,
    this.error,
  });

  final List<PostBaseDto> items;
  final List<String> seenItemIds;
  final String? nextCursor;
  final bool isLoading;
  final String? error;

  bool get hasMore => nextCursor != null && nextCursor!.isNotEmpty;

  DiscoveryFeedState copyWith({
    List<PostBaseDto>? items,
    List<String>? seenItemIds,
    Object? nextCursor = _unset,
    bool? isLoading,
    Object? error = _unset,
  }) {
    return DiscoveryFeedState(
      items: items ?? this.items,
      seenItemIds: seenItemIds ?? this.seenItemIds,
      nextCursor: identical(nextCursor, _unset)
          ? this.nextCursor
          : nextCursor as String?,
      isLoading: isLoading ?? this.isLoading,
      error: identical(error, _unset) ? this.error : error as String?,
    );
  }
}

typedef DiscoveryFeedQuery = ({
  String category,
  String? identity,
  String? type,
});

/// 将 surface tab id 映射到统一 discovery feed 查询。
DiscoveryFeedQuery toDiscoveryFeedQuery(String tabId) {
  switch (tabId) {
    case 'following':
      return (category: 'following', identity: 'moment', type: null);
    case 'moment':
      return (category: 'moment', identity: 'moment', type: null);
    case 'work':
    case 'works':
      return (category: 'work', identity: 'work', type: null);
    case 'photo':
      return (category: 'photo', identity: 'work', type: 'image');
    case 'video':
      return (category: 'video', identity: 'work', type: 'video');
    case 'article':
      return (category: 'article', identity: 'work', type: 'article');
    default:
      return (category: tabId, identity: null, type: null);
  }
}

/// 按 tabId 管理多路 feed 的 Notifier
class DiscoveryFeedMapNotifier
    extends Notifier<Map<String, AsyncValue<DiscoveryFeedState>>> {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() => {};

  /// 解析取数查询：首页频道以 [homeChannelsProvider]（端默认 + 远程覆盖）的 feed_query 为真相源；
  /// 非首页频道（发现 tab photo/video/...）回退 [toDiscoveryFeedQuery]。
  DiscoveryFeedQuery _resolveQuery(String tabId) {
    for (final channel in ref.read(homeChannelsProvider)) {
      if (channel.id != tabId) continue;
      final category = channel.feedQuery['category'];
      if (category != null && category.isNotEmpty) {
        return (
          category: category,
          identity: channel.feedQuery['identity'],
          type: channel.feedQuery['type'],
        );
      }
    }
    return toDiscoveryFeedQuery(tabId);
  }

  Future<void> load(String tabId, {bool force = false}) async {
    final currentValue = state[tabId]?.value;
    if (!force && currentValue != null && currentValue.items.isNotEmpty) {
      return;
    }
    final repo = ref.read(contentRepositoryProvider);
    final query = _resolveQuery(tabId);
    final feedSession = ref.read(feedSessionProvider.notifier);
    final sessionId = feedSession.sessionId;
    final feedRequestId = feedSession.newFeedRequestId();
    state = {...state, tabId: const AsyncLoading()};
    try {
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: null,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(page.items);
      final seen = page.items
          .map((item) => item.id)
          .where((id) => id.isNotEmpty)
          .toList(growable: false);
      state = {
        ...state,
        tabId: AsyncData(
          DiscoveryFeedState(
            items: page.items,
            seenItemIds: seen,
            nextCursor: page.nextCursor,
          ),
        ),
      };
    } catch (e, st) {
      developer.log('load error: $e', name: 'DiscoveryFeed', error: e, stackTrace: st);
      state = {
        ...state,
        tabId: AsyncData(
          DiscoveryFeedState(error: runtimeErrorDisplayMessage(e)),
        ),
      };
    }
  }

  Future<void> appendNextPage(String tabId) async {
    final current = state[tabId];
    final value = current?.value;
    if (value == null ||
        value.nextCursor == null ||
        value.nextCursor!.isEmpty ||
        value.isLoading) {
      return;
    }
    state = {
      ...state,
      tabId: AsyncData(value.copyWith(isLoading: true, error: null)),
    };
    try {
      final repo = ref.read(contentRepositoryProvider);
      final query = _resolveQuery(tabId);
      final feedSession = ref.read(feedSessionProvider.notifier);
      final sessionId = feedSession.sessionId;
      final feedRequestId = feedSession.newFeedRequestId();
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: value.nextCursor,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(page.items);
      final seen = value.seenItemIds.toSet();
      final dedupedNew = page.items
          .where((item) => !seen.contains(item.id))
          .toList(growable: false);
      final merged = <PostBaseDto>[...value.items, ...dedupedNew];
      final mergedSeen = <String>[
        ...value.seenItemIds,
        ...dedupedNew.map((e) => e.id),
      ];
      state = {
        ...state,
        tabId: AsyncData(
          value.copyWith(
            items: merged,
            seenItemIds: mergedSeen,
            nextCursor: page.nextCursor,
            isLoading: false,
            error: null,
          ),
        ),
      };
    } catch (e, st) {
      developer.log('append error: $e', name: 'DiscoveryFeed', error: e, stackTrace: st);
      state = {
        ...state,
        tabId: AsyncData(
          value.copyWith(
            isLoading: false,
            error: runtimeErrorDisplayMessage(e),
          ),
        ),
      };
    }
  }
}

/// 全量 feed 状态 Map 的 Provider
final discoveryFeedMapProvider =
    NotifierProvider<
      DiscoveryFeedMapNotifier,
      Map<String, AsyncValue<DiscoveryFeedState>>
    >(DiscoveryFeedMapNotifier.new);

/// 按 tab (photo/video) 读取当前 feed；首次访问时需调用 notifier.load(tabId)
final discoveryFeedProvider =
    Provider.family<AsyncValue<DiscoveryFeedState>, String>((ref, tabId) {
      final map = ref.watch(discoveryFeedMapProvider);
      return map[tabId] ?? const AsyncValue.loading();
    });
