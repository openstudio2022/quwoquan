import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/post_models.dart';

/// Feed数据状态
class FeedState {
  final Map<String, List<Post>> feedData;
  final Map<String, bool> isLoading;
  final Map<String, String?> errorMessages;
  final Map<String, bool> hasMore;
  final Map<String, int> currentPage;

  const FeedState({
    this.feedData = const {},
    this.isLoading = const {},
    this.errorMessages = const {},
    this.hasMore = const {},
    this.currentPage = const {},
  });

  FeedState copyWith({
    Map<String, List<Post>>? feedData,
    Map<String, bool>? isLoading,
    Map<String, String?>? errorMessages,
    Map<String, bool>? hasMore,
    Map<String, int>? currentPage,
  }) {
    return FeedState(
      feedData: feedData ?? this.feedData,
      isLoading: isLoading ?? this.isLoading,
      errorMessages: errorMessages ?? this.errorMessages,
      hasMore: hasMore ?? this.hasMore,
      currentPage: currentPage ?? this.currentPage,
    );
  }
}

/// Feed状态管理器
class FeedNotifier extends Notifier<FeedState> {
  @override
  FeedState build() {
    return const FeedState();
  }

  /// 获取数据服务
  DataService get _dataService => ref.read(dataServiceProvider);

  /// 加载Feed数据
  Future<void> loadFeedData(String tab, {bool refresh = false}) async {
    if (refresh) {
      // 刷新时重置状态
      state = state.copyWith(
        currentPage: {...state.currentPage, tab: 1},
        errorMessages: {...state.errorMessages, tab: null},
      );
    }

    // 设置加载状态
    state = state.copyWith(
      isLoading: {...state.isLoading, tab: true},
    );

    try {
      final currentPageNum = state.currentPage[tab] ?? 1;
      final postsData = await _dataService.getDataList(
        endpoint: '/posts',
        params: {'category': tab},
        limit: 20,
      );

      if (postsData.isNotEmpty) {
        final posts = postsData.map((json) => Post.fromJson(json)).toList();
        
        // 更新Feed数据
        final existingPosts = refresh ? <Post>[] : (state.feedData[tab] ?? []);
        final updatedPosts = [...existingPosts, ...posts];
        
        state = state.copyWith(
          feedData: {...state.feedData, tab: updatedPosts},
          isLoading: {...state.isLoading, tab: false},
          errorMessages: {...state.errorMessages, tab: null},
          hasMore: {...state.hasMore, tab: posts.length >= 20}, // 假设每页20条
          currentPage: {...state.currentPage, tab: currentPageNum + 1},
        );
      } else {
        throw Exception('没有更多数据');
      }
    } catch (error) {
      state = state.copyWith(
        isLoading: {...state.isLoading, tab: false},
        errorMessages: {...state.errorMessages, tab: error.toString()},
      );
    }
  }

  /// 刷新Feed数据
  Future<void> refreshFeedData(String tab) async {
    await loadFeedData(tab, refresh: true);
  }

  /// 加载更多数据
  Future<void> loadMoreData(String tab) async {
    if (state.isLoading[tab] == true || state.hasMore[tab] == false) {
      return;
    }
    await loadFeedData(tab);
  }

  /// 清除错误信息
  void clearError(String tab) {
    state = state.copyWith(
      errorMessages: {...state.errorMessages, tab: null},
    );
  }

  /// 重置所有状态
  void reset() {
    state = const FeedState();
  }
}

/// Feed状态提供者
final feedProvider = StateNotifierProvider<FeedNotifier, FeedState>((ref) {
  return FeedNotifier(ref);
});

/// 便捷访问器
final feedDataProvider = Provider.family<List<Post>, String>((ref, tab) {
  return ref.watch(feedProvider.select((state) => state.feedData[tab] ?? []));
});

final isFeedLoadingProvider = Provider.family<bool, String>((ref, tab) {
  return ref.watch(feedProvider.select((state) => state.isLoading[tab] ?? false));
});

final feedErrorProvider = Provider.family<String?, String>((ref, tab) {
  return ref.watch(feedProvider.select((state) => state.errorMessages[tab]));
});

final hasMoreFeedProvider = Provider.family<bool, String>((ref, tab) {
  return ref.watch(feedProvider.select((state) => state.hasMore[tab] ?? false));
});

