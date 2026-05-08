import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

/// 单类 feed 状态：items + nextCursor
class DiscoveryFeedState {
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

  DiscoveryFeedState copyWith({
    List<PostBaseDto>? items,
    List<String>? seenItemIds,
    String? nextCursor,
    bool? isLoading,
    String? error,
  }) {
    return DiscoveryFeedState(
      items: items ?? this.items,
      seenItemIds: seenItemIds ?? this.seenItemIds,
      nextCursor: nextCursor ?? this.nextCursor,
      isLoading: isLoading ?? this.isLoading,
      error: error ?? this.error,
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

  Future<void> load(String tabId, {bool force = false}) async {
    final currentValue = state[tabId]?.value;
    if (!force && currentValue != null && currentValue.items.isNotEmpty) {
      return;
    }
    final repo = ref.read(contentRepositoryProvider);
    final query = toDiscoveryFeedQuery(tabId);
    state = {...state, tabId: const AsyncLoading()};
    try {
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: null,
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
      debugPrint('DiscoveryFeedMapNotifier load error: $e $st');
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
    state = {...state, tabId: AsyncData(value.copyWith(isLoading: true))};
    try {
      final repo = ref.read(contentRepositoryProvider);
      final query = toDiscoveryFeedQuery(tabId);
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: value.nextCursor,
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
          ),
        ),
      };
    } catch (e, st) {
      debugPrint('DiscoveryFeedMapNotifier append error: $e $st');
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
