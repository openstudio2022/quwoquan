import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/post_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/story_models.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_snapshot.dart';

/// Content Post 发现体验的对象内 UI 状态；所有集合更新须用新实例赋值以保证 `ref.watch` 能感知变化。
///
/// 点赞/分享等互动事实的唯一真相源是 `postInteractionStateProvider`（全局投影
/// + outbox），本状态只承载发现页自身的 tab/feed/加载态，禁止再维护第二份
/// liked/count 副本。
class DiscoveryUiState {
  const DiscoveryUiState({
    this.activeTab = 'following',
    this.photographyCategory = 'all',
    this.feedData = const <String, List<Post>>{},
    this.isLoading = const <String, bool>{},
    this.errorMessages = const <String, String?>{},
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
  final List<Story> stories;
  final bool isStoriesLoading;
  final String? currentUser;
  final PersonaProfileSnapshot? userProfileData;
  final bool isUserProfileLoading;

  DiscoveryUiState copyWith({
    String? activeTab,
    String? photographyCategory,
    Map<String, List<Post>>? feedData,
    Map<String, bool>? isLoading,
    Map<String, String?>? errorMessages,
    List<Story>? stories,
    bool? isStoriesLoading,
    String? currentUser,
    PersonaProfileSnapshot? userProfileData,
    bool? isUserProfileLoading,
    bool clearCurrentUser = false,
  }) {
    return DiscoveryUiState(
      activeTab: activeTab ?? this.activeTab,
      photographyCategory: photographyCategory ?? this.photographyCategory,
      feedData: feedData ?? this.feedData,
      isLoading: isLoading ?? this.isLoading,
      errorMessages: errorMessages ?? this.errorMessages,
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

  void setUserProfileData(PersonaProfileSnapshot? user) {
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
