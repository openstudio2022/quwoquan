import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/data/services/data_service_provider.dart';
import 'package:quwoquan_app/features/profile/models/post_models.dart';
import 'package:quwoquan_app/features/home/models/story_models.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';

// 类型别名
typedef Post = PostModel;

// 首页状态数据类
class HomeStateData {
  // Tab导航状态
  final String activeTab;
  final String photographyCategory;
  
  // Feed数据状态
  final Map<String, List<Post>> feedData;
  final Map<String, bool> isLoading;
  final Map<String, String?> errorMessages;
  
  // 交互状态
  final Set<String> followingUsers;
  final Set<String> savedPosts;
  final Set<String> likedPosts;
  final Map<String, int> postLikesCount;
  final Map<String, int> postBookmarksCount;
  final Map<String, int> postSharesCount;
  
  // Stories状态
  final List<Story> stories;
  final bool isStoriesLoading;
  
  // 用户资料状态
  final String? currentUser;
  final User? userProfileData;
  final bool isUserProfileLoading;

  const HomeStateData({
    this.activeTab = 'following',
    this.photographyCategory = 'all',
    this.feedData = const {},
    this.isLoading = const {},
    this.errorMessages = const {},
    this.followingUsers = const {'nature_photographer', 'travel_photographer'},
    this.savedPosts = const {},
    this.likedPosts = const {},
    this.postLikesCount = const {},
    this.postBookmarksCount = const {},
    this.postSharesCount = const {},
    this.stories = const [],
    this.isStoriesLoading = false,
    this.currentUser,
    this.userProfileData,
    this.isUserProfileLoading = false,
  });

  HomeStateData copyWith({
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
  }) {
    return HomeStateData(
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
      currentUser: currentUser ?? this.currentUser,
      userProfileData: userProfileData ?? this.userProfileData,
      isUserProfileLoading: isUserProfileLoading ?? this.isUserProfileLoading,
    );
  }
}

// 首页状态管理器
class HomeNotifier extends Notifier<HomeStateData> {
  @override
  HomeStateData build() {
    return const HomeStateData();
  }
  
  // Tab管理
  void setActiveTab(String tab) {
    state = state.copyWith(activeTab: tab);
  }
  
  void setPhotographyCategory(String category) {
    state = state.copyWith(photographyCategory: category);
  }
  
  // Feed数据管理
  void setFeedData(String tab, List<Post> posts) {
    final newFeedData = Map<String, List<Post>>.from(state.feedData);
    newFeedData[tab] = posts;
    state = state.copyWith(feedData: newFeedData);
  }
  
  void setLoading(String tab, bool loading) {
    final newIsLoading = Map<String, bool>.from(state.isLoading);
    newIsLoading[tab] = loading;
    state = state.copyWith(isLoading: newIsLoading);
  }
  
  void setError(String tab, String? error) {
    final newErrorMessages = Map<String, String?>.from(state.errorMessages);
    newErrorMessages[tab] = error;
    state = state.copyWith(errorMessages: newErrorMessages);
  }
  
  void clearError(String tab) {
    final newErrorMessages = Map<String, String?>.from(state.errorMessages);
    newErrorMessages.remove(tab);
    state = state.copyWith(errorMessages: newErrorMessages);
  }
  
  // 交互状态管理
  void toggleFollow(String username) {
    final newFollowingUsers = Set<String>.from(state.followingUsers);
    if (newFollowingUsers.contains(username)) {
      newFollowingUsers.remove(username);
    } else {
      newFollowingUsers.add(username);
    }
    state = state.copyWith(followingUsers: newFollowingUsers);
  }
  
  void toggleLike(String postId) {
    final newLikedPosts = Set<String>.from(state.likedPosts);
    final newPostLikesCount = Map<String, int>.from(state.postLikesCount);
    
    if (newLikedPosts.contains(postId)) {
      newLikedPosts.remove(postId);
      final currentCount = newPostLikesCount[postId] ?? 0;
      newPostLikesCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      newLikedPosts.add(postId);
      final currentCount = newPostLikesCount[postId] ?? 0;
      newPostLikesCount[postId] = currentCount + 1;
    }
    state = state.copyWith(
      likedPosts: newLikedPosts,
      postLikesCount: newPostLikesCount,
    );
  }
  
  void toggleSave(String postId) {
    final newSavedPosts = Set<String>.from(state.savedPosts);
    final newPostBookmarksCount = Map<String, int>.from(state.postBookmarksCount);
    
    if (newSavedPosts.contains(postId)) {
      newSavedPosts.remove(postId);
      final currentCount = newPostBookmarksCount[postId] ?? 0;
      newPostBookmarksCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      newSavedPosts.add(postId);
      final currentCount = newPostBookmarksCount[postId] ?? 0;
      newPostBookmarksCount[postId] = currentCount + 1;
    }
    state = state.copyWith(
      savedPosts: newSavedPosts,
      postBookmarksCount: newPostBookmarksCount,
    );
  }
  
  void incrementShares(String postId) {
    final newPostSharesCount = Map<String, int>.from(state.postSharesCount);
    final currentCount = newPostSharesCount[postId] ?? 0;
    newPostSharesCount[postId] = currentCount + 1;
    state = state.copyWith(postSharesCount: newPostSharesCount);
  }
  
  // 获取帖子统计数据
  int getPostLikesCount(String postId) {
    return state.postLikesCount[postId] ?? 0;
  }
  
  int getPostBookmarksCount(String postId) {
    return state.postBookmarksCount[postId] ?? 0;
  }
  
  int getPostSharesCount(String postId) {
    return state.postSharesCount[postId] ?? 0;
  }
  
  // Stories管理
  void setStories(List<Story> stories) {
    state = state.copyWith(stories: stories);
  }
  
  void setStoriesLoading(bool loading) {
    state = state.copyWith(isStoriesLoading: loading);
  }
  
  // 用户资料管理
  void setCurrentUser(String? username) {
    state = state.copyWith(currentUser: username);
  }
  
  void setUserProfileData(User? user) {
    state = state.copyWith(userProfileData: user);
  }
  
  void setUserProfileLoading(bool loading) {
    state = state.copyWith(isUserProfileLoading: loading);
  }
  
  // 重置状态
  void reset() {
    state = const HomeStateData();
  }
}

// 首页状态提供者
final homeStateProvider = NotifierProvider<HomeNotifier, HomeStateData>(() {
  return HomeNotifier();
});

// 便捷访问器
final activeTabProvider = Provider<String>((ref) {
  return ref.watch(homeStateProvider).activeTab;
});

final feedDataProvider = Provider<Map<String, List<Post>>>((ref) {
  return ref.watch(homeStateProvider).feedData;
});

final followingUsersProvider = Provider<Set<String>>((ref) {
  return ref.watch(homeStateProvider).followingUsers;
});

final likedPostsProvider = Provider<Set<String>>((ref) {
  return ref.watch(homeStateProvider).likedPosts;
});

final savedPostsProvider = Provider<Set<String>>((ref) {
  return ref.watch(homeStateProvider).savedPosts;
});

