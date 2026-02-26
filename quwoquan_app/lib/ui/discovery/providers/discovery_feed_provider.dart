import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 单类 feed 状态：items + nextCursor
class DiscoveryFeedState {
  const DiscoveryFeedState({
    this.items = const [],
    this.nextCursor,
    this.isLoading = false,
    this.error,
  });

  final List<PostBaseDto> items;
  final String? nextCursor;
  final bool isLoading;
  final String? error;

  DiscoveryFeedState copyWith({
    List<PostBaseDto>? items,
    String? nextCursor,
    bool? isLoading,
    String? error,
  }) {
    return DiscoveryFeedState(
      items: items ?? this.items,
      nextCursor: nextCursor ?? this.nextCursor,
      isLoading: isLoading ?? this.isLoading,
      error: error ?? this.error,
    );
  }
}

/// 将 app tab id (photo/video) 映射为 feed API category
String toFeedCategory(String tabId) {
  return GeneratedPostRuntimeMetadata.appTabToFeedCategory[tabId] ?? 'images';
}

/// 按 tabId 管理多路 feed 的 Notifier
class DiscoveryFeedMapNotifier extends Notifier<Map<String, AsyncValue<DiscoveryFeedState>>> {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() => {};

  Future<void> load(String tabId) async {
    final repo = ref.read(contentRepositoryProvider);
    final category = toFeedCategory(tabId);
    state = {...state, tabId: const AsyncLoading()};
    try {
      final page = await repo.listDiscoveryFeedPage(
        category: category,
        limit: GeneratedPostRuntimeMetadata.feedDefaultLimit,
        cursor: null,
      );
      state = {
        ...state,
        tabId: AsyncData(DiscoveryFeedState(
          items: page.items,
          nextCursor: page.nextCursor,
        )),
      };
    } catch (e, st) {
      debugPrint('DiscoveryFeedMapNotifier load error: $e $st');
      state = {
        ...state,
        tabId: AsyncData(DiscoveryFeedState(error: e.toString())),
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
      tabId: AsyncData(value.copyWith(isLoading: true)),
    };
    try {
      final repo = ref.read(contentRepositoryProvider);
      final category = toFeedCategory(tabId);
      final page = await repo.listDiscoveryFeedPage(
        category: category,
        limit: GeneratedPostRuntimeMetadata.feedDefaultLimit,
        cursor: value.nextCursor,
      );
      final merged = <PostBaseDto>[...value.items, ...page.items];
      state = {
        ...state,
        tabId: AsyncData(value.copyWith(
          items: merged,
          nextCursor: page.nextCursor,
          isLoading: false,
        )),
      };
    } catch (e, st) {
      debugPrint('DiscoveryFeedMapNotifier append error: $e $st');
      state = {
        ...state,
        tabId: AsyncData(value.copyWith(isLoading: false, error: e.toString())),
      };
    }
  }
}

/// 全量 feed 状态 Map 的 Provider
final discoveryFeedMapProvider =
    NotifierProvider<DiscoveryFeedMapNotifier, Map<String, AsyncValue<DiscoveryFeedState>>>(
  DiscoveryFeedMapNotifier.new,
);

/// 按 tab (photo/video) 读取当前 feed；首次访问时需调用 notifier.load(tabId)
final discoveryFeedProvider =
    Provider.family<AsyncValue<DiscoveryFeedState>, String>((ref, tabId) {
  final map = ref.watch(discoveryFeedMapProvider);
  return map[tabId] ?? const AsyncValue.loading();
});
