import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/core/models/post_models.dart';
import 'package:quwoquan_app/core/models/story_models.dart';
import 'package:quwoquan_app/core/models/user_models.dart';

// 发现页状态管理器
class DiscoveryState extends ChangeNotifier {
  // Tab导航状态
  String _activeTab = 'following';
  String _photographyCategory = 'all';
  
  // Feed数据状态
  final Map<String, List<Post>> _feedData = {};
  final Map<String, bool> _isLoading = {};
  final Map<String, String?> _errorMessages = {};
  
  // 交互状态（使用非 final，每次修改创建新实例，确保 didUpdateWidget 能检测到变化）
  Set<String> _followingUsers = {'nature_photographer', 'travel_photographer'};
  Set<String> _savedPosts = <String>{};
  Set<String> _likedPosts = <String>{};
  final Map<String, int> _postLikesCount = <String, int>{};
  final Map<String, int> _postBookmarksCount = <String, int>{};
  final Map<String, int> _postSharesCount = <String, int>{};
  
  // Stories状态
  List<Story> _stories = [];
  bool _isStoriesLoading = false;
  
  // 用户资料状态
  String? _currentUser;
  User? _userProfileData;
  bool _isUserProfileLoading = false;
  
  // Getters
  String get activeTab => _activeTab;
  String get photographyCategory => _photographyCategory;
  Map<String, List<Post>> get feedData => _feedData;
  Map<String, bool> get isLoading => _isLoading;
  Map<String, String?> get errorMessages => _errorMessages;
  Set<String> get followingUsers => _followingUsers;
  Set<String> get savedPosts => _savedPosts;
  Set<String> get likedPosts => _likedPosts;
  List<Story> get stories => _stories;
  bool get isStoriesLoading => _isStoriesLoading;
  String? get currentUser => _currentUser;
  User? get userProfileData => _userProfileData;
  bool get isUserProfileLoading => _isUserProfileLoading;
  
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
      _followingUsers = Set.from(_followingUsers)..remove(username);
    } else {
      _followingUsers = {..._followingUsers, username};
    }
    notifyListeners();
  }
  
  /// [baseLikesCount] 帖子原始点赞数，首次点赞时用于与本地状态合并，保证详情与列表一致
  void toggleLike(String postId, {int? baseLikesCount}) {
    if (_likedPosts.contains(postId)) {
      _likedPosts = Set.from(_likedPosts)..remove(postId);
      final currentCount = _postLikesCount[postId] ?? baseLikesCount ?? 0;
      _postLikesCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      _likedPosts = {..._likedPosts, postId};
      final currentCount = _postLikesCount[postId] ?? baseLikesCount ?? 0;
      _postLikesCount[postId] = currentCount + 1;
    }
    notifyListeners();
  }

  /// [baseBookmarksCount] 帖子原始收藏数，首次收藏时用于与本地状态合并
  void toggleSave(String postId, {int? baseBookmarksCount}) {
    if (_savedPosts.contains(postId)) {
      _savedPosts = Set.from(_savedPosts)..remove(postId);
      final currentCount = _postBookmarksCount[postId] ?? baseBookmarksCount ?? 0;
      _postBookmarksCount[postId] = (currentCount - 1).clamp(0, double.infinity).toInt();
    } else {
      _savedPosts = {..._savedPosts, postId};
      final currentCount = _postBookmarksCount[postId] ?? baseBookmarksCount ?? 0;
      _postBookmarksCount[postId] = currentCount + 1;
    }
    notifyListeners();
  }
  
  void incrementShares(String postId) {
    final currentCount = _postSharesCount[postId] ?? 0;
    _postSharesCount[postId] = currentCount + 1;
    notifyListeners();
  }
  
  /// 优先返回本地维护的展示数；未操作过时返回 0，由调用方用帖子原始数兜底
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

// 发现页状态提供者：使用 ChangeNotifierProvider 订阅 notifyListeners 变更
final discoveryStateProvider = ChangeNotifierProvider<DiscoveryState>((ref) {
  final state = DiscoveryState();
  ref.onDispose(() => state.dispose());
  return state;
});

// 便捷访问器
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
