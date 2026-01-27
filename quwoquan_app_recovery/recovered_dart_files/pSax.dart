import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/post_models.dart';
import 'package:quwoquan_app/features/profile/models/story_models.dart';
import '../../profile/models/user_models.dart';

// 首页状态管理器
class HomeState extends ChangeNotifier {
  // Tab导航状态
  String _activeTab = 'following';
  String _photographyCategory = 'all';
  
  // Feed数据状态
  Map<String, List<Post>> _feedData = {};
  Map<String, bool> _isLoading = {};
  final Map<String, String?> _errorMessages = {};
  
  // 交互状态
  final Set<String> _followingUsers = {'nature_photographer', 'travel_photographer'};
  final Set<String> _savedPosts = <String>{};
  final Set<String> _likedPosts = <String>{};
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

