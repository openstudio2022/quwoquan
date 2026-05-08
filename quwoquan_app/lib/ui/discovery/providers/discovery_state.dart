import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/post_models.dart';
import 'package:quwoquan_app/core/models/story_models.dart';
import 'package:quwoquan_app/core/models/user_models.dart';

/// 发现页 UI 不可变快照；所有集合更新须用新实例赋值以保证 `ref.watch` 能感知变化。
class DiscoveryUiState {
  const DiscoveryUiState({
    this.activeTab = 'following',
    this.photographyCategory = 'all',
    this.feedData = const <String, List<Post>>{},
    this.isLoading = const <String, bool>{},
    this.errorMessages = const <String, String?>{},
    this.followingUsers = const {'nature_photographer', 'travel_photographer'},
    this.savedPosts = const <String>{},
    this.likedPosts = const <String>{},
    this.postLikesCount = const <String, int>{},
    this.postBookmarksCount = const <String, int>{},
    this.postSharesCount = const <String, int>{},
    this.stories = const <Story>[],
    this.isStoriesLoading = false,
    this.currentUser,
    this.userProfileData,
    this.isUserProfileLoading = false,
  });

  final String activeTab;
  final String photographyCategory;
  final Map<String, List<Post>> feedData;
  final Map<String, bool> isLoading;
  final Map<String, String?> errorMessages;
  final Set<String> followingUsers;
  final Set<String> savedPosts;
  final Set<String> likedPosts;
  final Map<String, int> postLikesCount;
  final Map<String, int> postBookmarksCount;
  final Map<String, int> postSharesCount;
  final List<Story> stories;
  final bool isStoriesLoading;
  final String? currentUser;
  final User? userProfileData;
  final bool isUserProfileLoading;

  /// 优先返回本地维护的展示数；未操作过时返回 0，由调用方用帖子原始数兜底
  int getPostLikesCount(String postId) => postLikesCount[postId] ?? 0;

  int getPostBookmarksCount(String postId) => postBookmarksCount[postId] ?? 0;

  int getPostSharesCount(String postId) => postSharesCount[postId] ?? 0;

  DiscoveryUiState copyWith({
    String? activeTab,
    String? photographyCategory,
    Map<String, List<Post>>? feedData,
    Map<String, bool>? isLoading,
    Map<String, String?>? errorMessages,
    Set<String>? followingUsers,
    Set<String>? savedPosts,
    Set<String>? likedPosts,
    Map<String, int>? postLikesCount,
    Map<String, int>? postBookmarksCount,
    Map<String, int>? postSharesCount,
    List<Story>? stories,
    bool? isStoriesLoading,
    String? currentUser,
    User? userProfileData,
    bool? isUserProfileLoading,
    bool clearCurrentUser = false,
  }) {
    return DiscoveryUiState(
      activeTab: activeTab ?? this.activeTab,
      photographyCategory: photographyCategory ?? this.photographyCategory,
      feedData: feedData ?? this.feedData,
      isLoading: isLoading ?? this.isLoading,
      errorMessages: errorMessages ?? this.errorMessages,
      followingUsers: followingUsers ?? this.followingUsers,
      savedPosts: savedPosts ?? this.savedPosts,
      likedPosts: likedPosts ?? this.likedPosts,
      postLikesCount: postLikesCount ?? this.postLikesCount,
      postBookmarksCount: postBookmarksCount ?? this.postBookmarksCount,
      postSharesCount: postSharesCount ?? this.postSharesCount,
      stories: stories ?? this.stories,
      isStoriesLoading: isStoriesLoading ?? this.isStoriesLoading,
      currentUser: clearCurrentUser ? null : (currentUser ?? this.currentUser),
      userProfileData: userProfileData ?? this.userProfileData,
      isUserProfileLoading: isUserProfileLoading ?? this.isUserProfileLoading,
    );
  }
}

class DiscoveryNotifier extends Notifier<DiscoveryUiState> {
  @override
  DiscoveryUiState build() => const DiscoveryUiState();

  void setActiveTab(String tab) {
    state = state.copyWith(activeTab: tab);
  }

  void setPhotographyCategory(String category) {
    state = state.copyWith(photographyCategory: category);
  }

  void setFeedData(String tab, List<Post> posts) {
    state = state.copyWith(
      feedData: Map<String, List<Post>>.from(state.feedData)..[tab] = posts,
    );
  }

  void setLoading(String tab, bool loading) {
    state = state.copyWith(
      isLoading: Map<String, bool>.from(state.isLoading)..[tab] = loading,
    );
  }

  void setError(String tab, String? error) {
    state = state.copyWith(
      errorMessages: Map<String, String?>.from(state.errorMessages)
        ..[tab] = error,
    );
  }

  void clearError(String tab) {
    final next = Map<String, String?>.from(state.errorMessages)..remove(tab);
    state = state.copyWith(errorMessages: next);
  }

  void toggleFollow(String username) {
    final next = state.followingUsers.contains(username)
        ? (Set<String>.from(state.followingUsers)..remove(username))
        : ({...state.followingUsers, username});
    state = state.copyWith(followingUsers: next);
  }

  void setFollowState(String subAccountId, bool isFollowing) {
    final next = Set<String>.from(state.followingUsers);
    if (isFollowing) {
      next.add(subAccountId);
    } else {
      next.remove(subAccountId);
    }
    state = state.copyWith(followingUsers: next);
  }

  /// [baseLikesCount] 帖子原始点赞数，首次点赞时用于与本地状态合并，保证详情与列表一致
  void toggleLike(String postId, {int? baseLikesCount}) {
    if (state.likedPosts.contains(postId)) {
      final liked = Set<String>.from(state.likedPosts)..remove(postId);
      final currentCount = state.postLikesCount[postId] ?? baseLikesCount ?? 0;
      final counts = Map<String, int>.from(state.postLikesCount)
        ..[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
      state = state.copyWith(likedPosts: liked, postLikesCount: counts);
    } else {
      final liked = {...state.likedPosts, postId};
      final currentCount = state.postLikesCount[postId] ?? baseLikesCount ?? 0;
      final counts = Map<String, int>.from(state.postLikesCount)
        ..[postId] = currentCount + 1;
      state = state.copyWith(likedPosts: liked, postLikesCount: counts);
    }
  }

  void setLikeState(String postId, bool isLiked, {int? likeCount}) {
    final liked = Set<String>.from(state.likedPosts);
    final counts = Map<String, int>.from(state.postLikesCount);
    if (isLiked) {
      liked.add(postId);
    } else {
      liked.remove(postId);
    }
    if (likeCount != null) {
      counts[postId] = likeCount;
    }
    state = state.copyWith(likedPosts: liked, postLikesCount: counts);
  }

  /// [baseBookmarksCount] 帖子原始收藏数，首次收藏时用于与本地状态合并
  void toggleSave(String postId, {int? baseBookmarksCount}) {
    if (state.savedPosts.contains(postId)) {
      final saved = Set<String>.from(state.savedPosts)..remove(postId);
      final currentCount =
          state.postBookmarksCount[postId] ?? baseBookmarksCount ?? 0;
      final counts = Map<String, int>.from(state.postBookmarksCount)
        ..[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
      state = state.copyWith(savedPosts: saved, postBookmarksCount: counts);
    } else {
      final saved = {...state.savedPosts, postId};
      final currentCount =
          state.postBookmarksCount[postId] ?? baseBookmarksCount ?? 0;
      final counts = Map<String, int>.from(state.postBookmarksCount)
        ..[postId] = currentCount + 1;
      state = state.copyWith(savedPosts: saved, postBookmarksCount: counts);
    }
  }

  void setSaveState(String postId, bool isSaved, {int? bookmarkCount}) {
    final saved = Set<String>.from(state.savedPosts);
    final counts = Map<String, int>.from(state.postBookmarksCount);
    if (isSaved) {
      saved.add(postId);
    } else {
      saved.remove(postId);
    }
    if (bookmarkCount != null) {
      counts[postId] = bookmarkCount;
    }
    state = state.copyWith(savedPosts: saved, postBookmarksCount: counts);
  }

  void incrementShares(String postId) {
    final currentCount = state.postSharesCount[postId] ?? 0;
    final counts = Map<String, int>.from(state.postSharesCount)
      ..[postId] = currentCount + 1;
    state = state.copyWith(postSharesCount: counts);
  }

  void setShareCount(String postId, int shareCount) {
    final counts = Map<String, int>.from(state.postSharesCount)
      ..[postId] = shareCount;
    state = state.copyWith(postSharesCount: counts);
  }

  void applyMediaViewerResult(MediaViewerResult result) {
    final scopePostIds = result.effectiveScopePostIds;
    final scopeProfileIds = result.effectiveScopeProfileIds;
    final nextFollowing = Set<String>.from(state.followingUsers);
    final nextSaved = Set<String>.from(state.savedPosts);
    final nextLiked = Set<String>.from(state.likedPosts);
    final nextLikeCounts = Map<String, int>.from(state.postLikesCount);
    final nextBookmarkCounts = Map<String, int>.from(state.postBookmarksCount);
    final nextShareCounts = Map<String, int>.from(state.postSharesCount);
    for (final profileId in scopeProfileIds) {
      if (result.followingUsers.contains(profileId)) {
        nextFollowing.add(profileId);
      } else {
        nextFollowing.remove(profileId);
      }
    }
    for (final postId in scopePostIds) {
      if (result.likedPosts.contains(postId)) {
        nextLiked.add(postId);
      } else {
        nextLiked.remove(postId);
      }
      if (result.savedPosts.contains(postId)) {
        nextSaved.add(postId);
      } else {
        nextSaved.remove(postId);
      }
      final likeCount = result.postLikesCount[postId];
      if (likeCount != null) {
        nextLikeCounts[postId] = likeCount;
      }
      final bookmarkCount = result.postBookmarksCount[postId];
      if (bookmarkCount != null) {
        nextBookmarkCounts[postId] = bookmarkCount;
      }
      final shareCount = result.postSharesCount[postId];
      if (shareCount != null) {
        nextShareCounts[postId] = shareCount;
      }
    }
    state = state.copyWith(
      followingUsers: nextFollowing,
      savedPosts: nextSaved,
      likedPosts: nextLiked,
      postLikesCount: nextLikeCounts,
      postBookmarksCount: nextBookmarkCounts,
      postSharesCount: nextShareCounts,
    );
  }

  void setStories(List<Story> stories) {
    state = state.copyWith(stories: stories);
  }

  void setStoriesLoading(bool loading) {
    state = state.copyWith(isStoriesLoading: loading);
  }

  void setCurrentUser(String? username) {
    state = state.copyWith(
      currentUser: username,
      clearCurrentUser: username == null,
    );
  }

  void setUserProfileData(User? user) {
    state = state.copyWith(userProfileData: user);
  }

  void setUserProfileLoading(bool loading) {
    state = state.copyWith(isUserProfileLoading: loading);
  }

  void reset() {
    state = const DiscoveryUiState();
  }
}

final discoveryStateProvider =
    NotifierProvider<DiscoveryNotifier, DiscoveryUiState>(
      DiscoveryNotifier.new,
    );

final activeTabProvider = Provider<String>((ref) {
  return ref.watch(discoveryStateProvider).activeTab;
});

final feedDataProvider = Provider<Map<String, List<Post>>>((ref) {
  return ref.watch(discoveryStateProvider).feedData;
});

final followingUsersProvider = Provider<Set<String>>((ref) {
  return ref.watch(discoveryStateProvider).followingUsers;
});

final likedPostsProvider = Provider<Set<String>>((ref) {
  return ref.watch(discoveryStateProvider).likedPosts;
});

final savedPostsProvider = Provider<Set<String>>((ref) {
  return ref.watch(discoveryStateProvider).savedPosts;
});
