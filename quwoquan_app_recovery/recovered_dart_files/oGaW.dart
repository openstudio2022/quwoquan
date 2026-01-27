import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/post_models.dart';
import 'package:quwoquan_app/features/profile/models/story_models.dart';
import '../../profile/models/user_models.dart';

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
    _activeTab = tab;
    notifyListeners();
  }
  
  void setPhotographyCategory(String category) {
    _photographyCategory = category;
    notifyListeners();
  }
  
  // Feed数据管理
  void setFeedData(String tab, List<Post> posts) {
    _feedData[tab] = posts;
    notifyListeners();
  }
  
  void setLoading(String tab, bool loading) {
    _isLoading[tab] = loading;
    notifyListeners();
  }
  
  void setError(String tab, String? error) {
    _errorMessages[tab] = error;
    notifyListeners();
  }
  
  void clearError(String tab) {
    _errorMessages.remove(tab);
    notifyListeners();
  }
  
  // 交互状态管理
  void toggleFollow(String username) {
    if (_followingUsers.contains(username)) {
      _followingUsers.remove(username);
    } else {
      _followingUsers.add(username);
    }
    notifyListeners();
  }
  
  void toggleLike(String postId) {
    if (_likedPosts.contains(postId)) {
      _likedPosts.remove(postId);
      final currentCount = _postLikesCount[postId] ?? 0;
      _postLikesCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      _likedPosts.add(postId);
      final currentCount = _postLikesCount[postId] ?? 0;
      _postLikesCount[postId] = currentCount + 1;
    }
    notifyListeners();
  }
  
  void toggleSave(String postId) {
    if (_savedPosts.contains(postId)) {
      _savedPosts.remove(postId);
      final currentCount = _postBookmarksCount[postId] ?? 0;
      _postBookmarksCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      _savedPosts.add(postId);
      final currentCount = _postBookmarksCount[postId] ?? 0;
      _postBookmarksCount[postId] = currentCount + 1;
    }
    notifyListeners();
  }
  
  void incrementShares(String postId) {
    final currentCount = _postSharesCount[postId] ?? 0;
    _postSharesCount[postId] = currentCount + 1;
    notifyListeners();
  }
  
  // 获取帖子统计数据
  int getPostLikesCount(String postId) {
    return _postLikesCount[postId] ?? 0;
  }
  
  int getPostBookmarksCount(String postId) {
    return _postBookmarksCount[postId] ?? 0;
  }
  
  int getPostSharesCount(String postId) {
    return _postSharesCount[postId] ?? 0;
  }
  
  // Stories管理
  void setStories(List<Story> stories) {
    _stories = stories;
    notifyListeners();
  }
  
  void setStoriesLoading(bool loading) {
    _isStoriesLoading = loading;
    notifyListeners();
  }
  
  // 用户资料管理
  void setCurrentUser(String? username) {
    _currentUser = username;
    notifyListeners();
  }
  
  void setUserProfileData(User? user) {
    _userProfileData = user;
    notifyListeners();
  }
  
  void setUserProfileLoading(bool loading) {
    _isUserProfileLoading = loading;
    notifyListeners();
  }
  
  // 重置状态
  void reset() {
    _activeTab = 'following';
    _photographyCategory = 'all';
    _feedData.clear();
    _isLoading.clear();
    _errorMessages.clear();
    _stories.clear();
    _isStoriesLoading = false;
    _currentUser = null;
    _userProfileData = null;
    _isUserProfileLoading = false;
    notifyListeners();
  }
}

// 首页状态提供者
final homeStateProvider = ChangeNotifierProvider<HomeState>((ref) {
  return HomeState();
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

