import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_interaction_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/call_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/invite_repository.dart';
import 'package:quwoquan_app/cloud/services/user/keyword_block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/client_state_sync.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/conversation_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/models/user_models.dart';

/// 主题相关的便捷Provider
final isDarkProvider = Provider<bool>((ref) {
  return ref.watch(effectiveIsDarkProvider);
});

enum AppBreakpoint { compact, regular, expanded }

class ResponsiveState {
  final Size size;
  final double devicePixelRatio;
  final Orientation orientation;
  final AppBreakpoint breakpoint;

  const ResponsiveState({
    this.size = Size.zero,
    this.devicePixelRatio = 1.0,
    this.orientation = Orientation.portrait,
    this.breakpoint = AppBreakpoint.regular,
  });

  ResponsiveState copyWith({
    Size? size,
    double? devicePixelRatio,
    Orientation? orientation,
    AppBreakpoint? breakpoint,
  }) {
    return ResponsiveState(
      size: size ?? this.size,
      devicePixelRatio: devicePixelRatio ?? this.devicePixelRatio,
      orientation: orientation ?? this.orientation,
      breakpoint: breakpoint ?? this.breakpoint,
    );
  }

  @override
  bool operator ==(Object other) {
    return other is ResponsiveState &&
        other.size == size &&
        other.devicePixelRatio == devicePixelRatio &&
        other.orientation == orientation &&
        other.breakpoint == breakpoint;
  }

  @override
  int get hashCode =>
      Object.hash(size, devicePixelRatio, orientation, breakpoint);
}

class ResponsiveNotifier extends Notifier<ResponsiveState> {
  @override
  ResponsiveState build() {
    return const ResponsiveState();
  }

  void updateFromMediaQueryData(MediaQueryData data) {
    updateFromSize(data.size, devicePixelRatio: data.devicePixelRatio);
  }

  void updateFromSize(Size size, {double devicePixelRatio = 1.0}) {
    final breakpoint = switch (size.width) {
      < 360 => AppBreakpoint.compact,
      >= 600 => AppBreakpoint.expanded,
      _ => AppBreakpoint.regular,
    };
    final orientation = size.width > size.height
        ? Orientation.landscape
        : Orientation.portrait;
    final next = ResponsiveState(
      size: size,
      devicePixelRatio: devicePixelRatio,
      orientation: orientation,
      breakpoint: breakpoint,
    );
    if (next == state) return;
    state = next;
  }
}

class AppearanceSnapshot {
  final ThemeMode themeMode;
  final Brightness effectiveBrightness;
  final bool isDark;
  final AppFontSizePreset fontSizePreset;
  final double textScaleFactor;
  final bool boldText;
  final bool highContrast;
  final AppBreakpoint breakpoint;
  final ResponsiveState responsiveState;

  const AppearanceSnapshot({
    required this.themeMode,
    required this.effectiveBrightness,
    required this.isDark,
    required this.fontSizePreset,
    required this.textScaleFactor,
    required this.boldText,
    required this.highContrast,
    required this.breakpoint,
    required this.responsiveState,
  });
}

/// 从 assistant 域退出时恢复的主底栏 tab。
/// 仅记录进入 assistant 前的上一个主 tab，避免多处维护数字索引语义。
final lastMainTabBeforeAssistantProvider =
    NotifierProvider<LastMainTabBeforeAssistantNotifier, MainTabDestination?>(
      LastMainTabBeforeAssistantNotifier.new,
    );

class LastMainTabBeforeAssistantNotifier extends Notifier<MainTabDestination?> {
  @override
  MainTabDestination? build() => null;

  void set(MainTabDestination? value) => state = value;
}

/// 助理页内部当前一级 tab（`schedule` / `dialog` / `skills`）。
/// 由主壳读取，用于决定助理路由下底部导航是否应当隐藏。
final assistantInternalTabProvider =
    NotifierProvider<AssistantInternalTabNotifier, String>(
      AssistantInternalTabNotifier.new,
    );

class AssistantInternalTabNotifier extends Notifier<String> {
  @override
  String build() => 'dialog';

  void set(String value) => state = value;
}

/// 用户数据Provider — 通过 UserProfileRepository 加载档案
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(String userId) async {
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      final profile = await repo.getUserProfile(userId);
      final avatarUrl = profile['avatarUrl']?.toString();
      final profileSubjectId =
          profile['profileSubjectId']?.toString() ??
          profile['userId']?.toString() ??
          userId;
      state = User(
        id: profileSubjectId,
        username:
            profile['username']?.toString() ??
            profile['nickname']?.toString() ??
            userId,
        displayName:
            profile['displayName']?.toString() ??
            profile['nickname']?.toString(),
        avatarUrl: avatarUrl,
        avatar: avatarUrl,
        bio: profile['bio']?.toString(),
        backgroundImage: profile['backgroundUrl']?.toString(),
        metadata: <String, dynamic>{
          'ownerUserId': profile['ownerUserId']?.toString(),
          'subAccountId': profile['subAccountId']?.toString(),
          'subjectType': profile['subjectType']?.toString(),
          'personaContextVersion': profile['personaContextVersion']?.toString(),
        },
      );
    } catch (_) {
      state = User(id: userId, username: userId);
    }
  }
}

final userDataProvider = NotifierProvider<UserDataNotifier, User?>(() {
  return UserDataNotifier();
});

/// 当前用户 ID — Mock/Remote 过渡期均使用 ChatMockData.currentUserProfileId；
/// auth 就绪后可改为 ref.watch(authRepositoryProvider).currentUserId。
final currentUserIdProvider = Provider<String>((ref) {
  final profileUserId = ref.watch(userDataProvider)?.id;
  if (profileUserId != null && profileUserId.isNotEmpty) {
    return profileUserId;
  }
  return ChatMockData.currentUserProfileId;
});

/// 响应式Provider
final responsiveProvider =
    NotifierProvider<ResponsiveNotifier, ResponsiveState>(() {
      return ResponsiveNotifier();
    });

/// 聚合后的全局外观快照，供根入口和共享组件消费。
final appearanceSnapshotProvider = Provider<AppearanceSnapshot>((ref) {
  final themeState = ref.watch(themeProvider);
  final accessibilityState = ref.watch(accessibilityProvider);
  final responsiveState = ref.watch(responsiveProvider);
  return AppearanceSnapshot(
    themeMode: themeState.themeMode,
    effectiveBrightness: themeState.effectiveBrightness,
    isDark: themeState.isDark,
    fontSizePreset: accessibilityState.fontSizePreset,
    textScaleFactor: accessibilityState.actualTextScaleFactor,
    boldText: accessibilityState.boldText,
    highContrast: accessibilityState.highContrast,
    breakpoint: responsiveState.breakpoint,
    responsiveState: responsiveState,
  );
});

/// 数据服务Provider
final dataServiceProvider = Provider<DataService>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    // 过渡层：UI 仍可调用 DataService，但底层已经按 ContentRepository（业务对象）组织。
    final repo = ref.watch(contentRepositoryProvider);
    return _LegacyContentDataService(repo);
  }
  return DataServiceImpl();
});

class _LegacyContentDataService implements DataService {
  _LegacyContentDataService(this._contentRepository);

  final ContentRepository _contentRepository;
  final List<Map<String, dynamic>> _localGeneratedPosts =
      <Map<String, dynamic>>[];

  List<Map<String, dynamic>> _mergeLocalGeneratedPosts({
    required List<Map<String, dynamic>> remoteItems,
    required String category,
  }) {
    final remoteIds = remoteItems
        .map((item) => item['id']?.toString() ?? '')
        .where((id) => id.isNotEmpty)
        .toSet();
    final local = _localGeneratedPosts
        .where(
          (post) =>
              _matchesCategory(post, category) &&
              !remoteIds.contains(post['id']?.toString() ?? ''),
        )
        .toList(growable: false);
    if (local.isEmpty) return remoteItems;
    return <Map<String, dynamic>>[...local, ...remoteItems];
  }

  bool _matchesCategory(Map<String, dynamic> post, String category) {
    final expectedFeedType =
        GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
    if (expectedFeedType == null || expectedFeedType.isEmpty) {
      return true;
    }
    final postType = (post['type'] ?? '').toString().trim();
    if (postType.isEmpty) return false;
    final normalizedPostType = switch (postType) {
      'image' => 'photo',
      _ => postType,
    };
    return normalizedPostType == expectedFeedType;
  }

  @override
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  }) async {
    if (endpoint == '/posts') {
      final category = (params?['category'] as String?) ?? 'recommended';
      final subCategory = params?['subCategory'] as String?;
      final cursor = params?['cursor'] as String?;
      final dtos = await _contentRepository.listDiscoveryFeed(
        category: category,
        subCategory: subCategory,
        cursor: cursor,
        limit: limit ?? GeneratedPostRuntimeMetadata.feedDefaultLimit,
      );
      final remoteItems = dtos
          .map((dto) => dto.toMap())
          .toList(growable: false);
      return _mergeLocalGeneratedPosts(
        remoteItems: remoteItems,
        category: category,
      );
    }
    throw UnimplementedError('LegacyDataService endpoint=$endpoint');
  }

  @override
  Future<Map<String, dynamic>> getDataItem({
    required String endpoint,
    required String id,
    Map<String, dynamic>? params,
  }) {
    if (endpoint == '/posts') {
      for (final post in _localGeneratedPosts) {
        if (post['id']?.toString() == id) {
          return Future<Map<String, dynamic>>.value(post);
        }
      }
      return _contentRepository.getPost(postId: id);
    }
    throw UnimplementedError(
      'LegacyDataService getDataItem endpoint=$endpoint',
    );
  }

  @override
  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  }) async {
    if (endpoint == '/posts') {
      final remotePost = await _contentRepository.createPost(payload: data);
      _localGeneratedPosts.insert(0, remotePost);
      return remotePost;
    }
    throw UnimplementedError(
      'LegacyDataService createDataItem endpoint=$endpoint',
    );
  }

  @override
  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  }) {
    if (endpoint == '/posts') {
      final index = _localGeneratedPosts.indexWhere(
        (post) => post['id']?.toString() == id,
      );
      if (index < 0) {
        throw UnsupportedError(
          'LegacyDataService updateDataItem only supports local-generated posts: $id',
        );
      }
      final updated = <String, dynamic>{
        ..._localGeneratedPosts[index],
        ...data,
        'updatedAt': DateTime.now().toIso8601String(),
      };
      _localGeneratedPosts[index] = updated;
      return Future<Map<String, dynamic>>.value(updated);
    }
    throw UnimplementedError(
      'LegacyDataService updateDataItem endpoint=$endpoint',
    );
  }

  @override
  Future<void> deleteDataItem({required String endpoint, required String id}) {
    if (endpoint == '/posts') {
      _localGeneratedPosts.removeWhere((post) => post['id']?.toString() == id);
      return Future<void>.value();
    }
    throw UnimplementedError(
      'LegacyDataService deleteDataItem endpoint=$endpoint',
    );
  }
}

/// 浏览记录服务 Provider（小趣基线：记录访问用于 experienceLevel）
final visitRecorderServiceProvider = Provider<VisitRecorderService>((ref) {
  return VisitRecorderService();
});

const Map<String, bool> _contentStoryBootstrapFlags = <String, bool>{
  'enable_create_action_entry': true,
  'enable_unified_create_editor': true,
  'simple_create_action_sheet': true,
  'create_editor_v2': true,
  'progressive_title_prompt': true,
  'enable_identity_based_surfaces': true,
  'enable_identity_share_template': true,
  'enable_assistant_content_identity_index': true,
};

class PersonalContentAccessState {
  const PersonalContentAccessState({
    required this.granted,
    required this.isHydrating,
    required this.isSyncing,
    required this.grantedScope,
    required this.source,
    this.updatedAt,
    this.errorMessage,
  });

  final bool granted;
  final bool isHydrating;
  final bool isSyncing;
  final String grantedScope;
  final String source;
  final DateTime? updatedAt;
  final String? errorMessage;

  String get summaryLabel => granted ? '已允许' : '未允许';

  PersonalContentAccessState copyWith({
    bool? granted,
    bool? isHydrating,
    bool? isSyncing,
    String? grantedScope,
    String? source,
    DateTime? updatedAt,
    String? errorMessage,
    bool clearError = false,
  }) {
    return PersonalContentAccessState(
      granted: granted ?? this.granted,
      isHydrating: isHydrating ?? this.isHydrating,
      isSyncing: isSyncing ?? this.isSyncing,
      grantedScope: grantedScope ?? this.grantedScope,
      source: source ?? this.source,
      updatedAt: updatedAt ?? this.updatedAt,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }

  factory PersonalContentAccessState.initial() {
    return const PersonalContentAccessState(
      granted: false,
      isHydrating: true,
      isSyncing: false,
      grantedScope: kPersonalContentAccessSkillId,
      source: 'bootstrap',
    );
  }
}

class PersonalContentAccessNotifier
    extends Notifier<PersonalContentAccessState> {
  bool _didScheduleHydration = false;

  @override
  PersonalContentAccessState build() {
    final initial = PersonalContentAccessState.initial();
    if (!_didScheduleHydration) {
      _didScheduleHydration = true;
      Future<void>.microtask(refresh);
    }
    return initial;
  }

  Future<void> refresh() async {
    state = state.copyWith(isHydrating: true, clearError: true);
    try {
      final consents = await ref
          .read(assistantRepositoryProvider)
          .listConsents();
      final current = consents.cast<AssistantSkillConsent?>().firstWhere(
        (item) => item?.skillId == kPersonalContentAccessSkillId,
        orElse: () => null,
      );
      if (current == null) {
        state = state.copyWith(
          granted: false,
          isHydrating: false,
          grantedScope: kPersonalContentAccessSkillId,
          source: 'repository',
          updatedAt: null,
          clearError: true,
        );
        return;
      }
      state = state.copyWith(
        granted: current.granted,
        isHydrating: false,
        grantedScope: current.grantedScope,
        source: 'repository',
        updatedAt: current.updatedAt,
        clearError: true,
      );
    } catch (error) {
      state = state.copyWith(
        isHydrating: false,
        errorMessage: error.toString(),
      );
    }
  }

  Future<void> setGranted(bool granted) async {
    state = state.copyWith(isSyncing: true, clearError: true);
    try {
      if (granted) {
        final consent = await ref
            .read(assistantRepositoryProvider)
            .grantSkillConsent(
              skillId: kPersonalContentAccessSkillId,
              grantedScope: kPersonalContentAccessSkillId,
            );
        state = state.copyWith(
          granted: consent.granted,
          grantedScope: consent.grantedScope,
          updatedAt: consent.updatedAt,
          source: 'repository',
          isHydrating: false,
          isSyncing: false,
          clearError: true,
        );
        return;
      }
      await ref
          .read(assistantRepositoryProvider)
          .revokeSkillConsent(skillId: kPersonalContentAccessSkillId);
      state = state.copyWith(
        granted: false,
        grantedScope: kPersonalContentAccessSkillId,
        updatedAt: DateTime.now(),
        source: 'repository',
        isHydrating: false,
        isSyncing: false,
        clearError: true,
      );
    } catch (error) {
      state = state.copyWith(isSyncing: false, errorMessage: error.toString());
    }
  }
}

class ContentCanaryStage {
  const ContentCanaryStage({required this.stage, required this.rolloutPercent});

  final String stage;
  final int rolloutPercent;

  factory ContentCanaryStage.fromMap(Map<String, dynamic> map) {
    return ContentCanaryStage(
      stage: (map['stage'] ?? '').toString().trim(),
      rolloutPercent: (map['rolloutPercent'] as num?)?.toInt() ?? 0,
    );
  }
}

class ContentRuntimeConfigState {
  const ContentRuntimeConfigState({
    required this.featureFlags,
    required this.experimentBucket,
    required this.currentCanaryStage,
    required this.canaryStages,
    required this.clientStateSync,
  });

  final Map<String, bool> featureFlags;
  final String experimentBucket;
  final String currentCanaryStage;
  final List<ContentCanaryStage> canaryStages;
  final ClientStateSyncConfig clientStateSync;

  bool isEnabled(String flag) => featureFlags[flag] ?? false;

  factory ContentRuntimeConfigState.defaults({
    required AppDataSourceMode mode,
  }) {
    final baseFlags = <String, bool>{...ContentUIConfig.featureFlags};
    if (mode != AppDataSourceMode.remote) {
      baseFlags.addAll(_contentStoryBootstrapFlags);
    }
    return ContentRuntimeConfigState(
      featureFlags: baseFlags,
      experimentBucket: mode == AppDataSourceMode.remote
          ? 'control'
          : 'local_story_enabled',
      currentCanaryStage: mode == AppDataSourceMode.remote ? 'control' : '100%',
      canaryStages: const <ContentCanaryStage>[
        ContentCanaryStage(stage: '5%', rolloutPercent: 5),
        ContentCanaryStage(stage: '20%', rolloutPercent: 20),
        ContentCanaryStage(stage: '50%', rolloutPercent: 50),
        ContentCanaryStage(stage: '100%', rolloutPercent: 100),
      ],
      clientStateSync: ClientStateSyncConfig.defaults(),
    );
  }

  factory ContentRuntimeConfigState.fromAppConfig(
    Map<String, dynamic> config, {
    required ContentRuntimeConfigState fallback,
  }) {
    final content =
        (config['content'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final rawFlags =
        (content['feature_flags'] as Map?)?.cast<String, dynamic>() ??
        (content['featureFlags'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final mergedFlags = <String, bool>{...fallback.featureFlags};
    for (final entry in rawFlags.entries) {
      final value = entry.value;
      if (value is bool) {
        mergedFlags[entry.key] = value;
      }
    }
    final grayRelease =
        (content['gray_release'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final rawStages =
        (grayRelease['canary_matrix'] as List?)
            ?.whereType<Map>()
            .map(
              (item) =>
                  ContentCanaryStage.fromMap(item.cast<String, dynamic>()),
            )
            .where((stage) => stage.stage.isNotEmpty)
            .toList(growable: false) ??
        fallback.canaryStages;
    final experimentBucket =
        (grayRelease['experiment_bucket'] ?? fallback.experimentBucket)
            .toString()
            .trim();
    final currentCanaryStage =
        (grayRelease['current_stage'] ?? fallback.currentCanaryStage)
            .toString()
            .trim();
    final rawClientStateSync =
        (content['client_state_sync'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return ContentRuntimeConfigState(
      featureFlags: mergedFlags,
      experimentBucket: experimentBucket.isEmpty
          ? fallback.experimentBucket
          : experimentBucket,
      currentCanaryStage: currentCanaryStage.isEmpty
          ? fallback.currentCanaryStage
          : currentCanaryStage,
      canaryStages: rawStages.isEmpty ? fallback.canaryStages : rawStages,
      clientStateSync: ClientStateSyncConfig.fromMap(
        rawClientStateSync,
        fallback: fallback.clientStateSync,
      ),
    );
  }
}

class ContentRuntimeConfigNotifier extends Notifier<ContentRuntimeConfigState> {
  bool _didScheduleRefresh = false;

  @override
  ContentRuntimeConfigState build() {
    final mode = ref.watch(appDataSourceModeProvider);
    final initial = ContentRuntimeConfigState.defaults(mode: mode);
    if (!_didScheduleRefresh) {
      _didScheduleRefresh = true;
      Future<void>.microtask(refresh);
    }
    return initial;
  }

  Future<void> refresh() async {
    final fallback = ContentRuntimeConfigState.defaults(
      mode: ref.read(appDataSourceModeProvider),
    );
    try {
      final remoteConfig = await ref
          .read(contentRepositoryProvider)
          .getAppConfig();
      state = ContentRuntimeConfigState.fromAppConfig(
        remoteConfig,
        fallback: fallback,
      );
    } catch (_) {
      state = fallback;
    }
  }
}

final contentRuntimeConfigProvider =
    NotifierProvider<ContentRuntimeConfigNotifier, ContentRuntimeConfigState>(
      ContentRuntimeConfigNotifier.new,
    );

final contentFeatureFlagProvider = Provider.family<bool, String>((ref, flag) {
  return ref.watch(contentRuntimeConfigProvider).isEnabled(flag);
});

class UserRelationshipState {
  const UserRelationshipState({this.followingProfileIds = const <String>{}});

  final Set<String> followingProfileIds;

  bool isFollowing(String profileSubjectId) {
    return followingProfileIds.contains(profileSubjectId);
  }

  UserRelationshipState copyWith({Set<String>? followingProfileIds}) {
    return UserRelationshipState(
      followingProfileIds: followingProfileIds ?? this.followingProfileIds,
    );
  }
}

class UserRelationshipStateNotifier extends Notifier<UserRelationshipState> {
  @override
  UserRelationshipState build() => const UserRelationshipState();

  void seedFollowing(Iterable<String> profileSubjectIds) {
    state = UserRelationshipState(
      followingProfileIds: Set<String>.from(profileSubjectIds),
    );
  }

  void setFollowing(String profileSubjectId, bool isFollowing) {
    final next = Set<String>.from(state.followingProfileIds);
    if (isFollowing) {
      next.add(profileSubjectId);
    } else {
      next.remove(profileSubjectId);
    }
    state = state.copyWith(followingProfileIds: next);
  }

  void applyViewerResult(MediaViewerResult result) {
    seedFollowing(result.followingUsers);
  }
}

class PostInteractionState {
  const PostInteractionState({
    this.likedPostIds = const <String>{},
    this.savedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.bookmarkCounts = const <String, int>{},
    this.shareCounts = const <String, int>{},
  });

  final Set<String> likedPostIds;
  final Set<String> savedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> bookmarkCounts;
  final Map<String, int> shareCounts;

  bool isLiked(String postId) => likedPostIds.contains(postId);
  bool isSaved(String postId) => savedPostIds.contains(postId);

  int likeCountFor(String postId, {int fallback = 0}) {
    return likeCounts[postId] ?? fallback;
  }

  int bookmarkCountFor(String postId, {int fallback = 0}) {
    return bookmarkCounts[postId] ?? fallback;
  }

  int shareCountFor(String postId, {int fallback = 0}) {
    return shareCounts[postId] ?? fallback;
  }

  PostInteractionState copyWith({
    Set<String>? likedPostIds,
    Set<String>? savedPostIds,
    Map<String, int>? likeCounts,
    Map<String, int>? bookmarkCounts,
    Map<String, int>? shareCounts,
  }) {
    return PostInteractionState(
      likedPostIds: likedPostIds ?? this.likedPostIds,
      savedPostIds: savedPostIds ?? this.savedPostIds,
      likeCounts: likeCounts ?? this.likeCounts,
      bookmarkCounts: bookmarkCounts ?? this.bookmarkCounts,
      shareCounts: shareCounts ?? this.shareCounts,
    );
  }
}

class PostInteractionStateNotifier extends Notifier<PostInteractionState> {
  @override
  PostInteractionState build() => const PostInteractionState();

  void setLiked(String postId, bool isLiked, {int? likeCount}) {
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextCounts = Map<String, int>.from(state.likeCounts);
    if (isLiked) {
      nextLiked.add(postId);
    } else {
      nextLiked.remove(postId);
    }
    if (likeCount != null) {
      nextCounts[postId] = likeCount;
    }
    state = state.copyWith(likedPostIds: nextLiked, likeCounts: nextCounts);
  }

  void setSaved(String postId, bool isSaved, {int? bookmarkCount}) {
    final nextSaved = Set<String>.from(state.savedPostIds);
    final nextCounts = Map<String, int>.from(state.bookmarkCounts);
    if (isSaved) {
      nextSaved.add(postId);
    } else {
      nextSaved.remove(postId);
    }
    if (bookmarkCount != null) {
      nextCounts[postId] = bookmarkCount;
    }
    state = state.copyWith(savedPostIds: nextSaved, bookmarkCounts: nextCounts);
  }

  void setShareCount(String postId, int shareCount) {
    final next = Map<String, int>.from(state.shareCounts);
    next[postId] = shareCount;
    state = state.copyWith(shareCounts: next);
  }

  void applyViewerResult(MediaViewerResult result) {
    state = PostInteractionState(
      likedPostIds: Set<String>.from(result.likedPosts),
      savedPostIds: Set<String>.from(result.savedPosts),
      likeCounts: Map<String, int>.from(result.postLikesCount),
      bookmarkCounts: Map<String, int>.from(result.postBookmarksCount),
      shareCounts: Map<String, int>.from(result.postSharesCount),
    );
  }
}

class ClientStateSyncOutboxNotifier
    extends Notifier<ClientStateSyncOutboxState> {
  Timer? _flushTimer;

  @override
  ClientStateSyncOutboxState build() {
    ref.onDispose(() {
      _flushTimer?.cancel();
    });
    return const ClientStateSyncOutboxState();
  }

  void enqueueFollow({
    required String profileSubjectId,
    required bool shouldFollow,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: profileSubjectId,
      intentType: 'follow',
      desiredBoolValue: shouldFollow,
    );
  }

  void enqueuePostLike({required String postId, required bool isLiked}) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'like',
      desiredBoolValue: isLiked,
    );
  }

  void enqueuePostSave({required String postId, required bool isSaved}) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'save',
      desiredBoolValue: isSaved,
    );
  }

  Future<void> flushNow() async {
    final config = ref.read(contentRuntimeConfigProvider).clientStateSync;
    final now = DateTime.now();
    final dueEntries = state.entries
        .where((entry) => !entry.nextFlushAt.isAfter(now))
        .take(config.maxBatchSize)
        .toList(growable: false);
    if (dueEntries.isEmpty) {
      _scheduleNextFlush();
      return;
    }

    var nextEntries = List<ClientStateSyncOutboxEntry>.from(state.entries);
    for (final entry in dueEntries) {
      try {
        await _flushEntry(entry);
        nextEntries.removeWhere(
          (item) => item.coalesceKey == entry.coalesceKey,
        );
      } catch (_) {
        nextEntries = nextEntries
            .map((item) {
              if (item.coalesceKey != entry.coalesceKey) {
                return item;
              }
              return item.copyWith(
                retryCount: item.retryCount + 1,
                nextFlushAt: now.add(config.retryDelay),
              );
            })
            .toList(growable: false);
      }
    }
    state = state.copyWith(entries: nextEntries);
    _scheduleNextFlush();
  }

  Future<void> _flushEntry(ClientStateSyncOutboxEntry entry) async {
    switch ('${entry.objectType}:${entry.intentType}') {
      case 'profile:follow':
        final repo = ref.read(userProfileRepositoryProvider);
        if (entry.desiredBoolValue) {
          await repo.followUser(entry.objectId);
        } else {
          await repo.unfollowUser(entry.objectId);
        }
        return;
      case 'post:like':
        final repo = ref.read(contentRepositoryProvider);
        if (entry.desiredBoolValue) {
          await repo.likePost(postId: entry.objectId);
        } else {
          await repo.unlikePost(postId: entry.objectId);
        }
        return;
      case 'post:save':
        final repo = ref.read(contentRepositoryProvider);
        if (entry.desiredBoolValue) {
          await repo.favoritePost(postId: entry.objectId);
        } else {
          await repo.unfavoritePost(postId: entry.objectId);
        }
        return;
    }
  }

  void _upsertEntry({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool desiredBoolValue,
  }) {
    final config = ref.read(contentRuntimeConfigProvider).clientStateSync;
    final coalesceKey = '$objectType:$intentType:$objectId';
    final entry = ClientStateSyncOutboxEntry(
      coalesceKey: coalesceKey,
      objectType: objectType,
      objectId: objectId,
      intentType: intentType,
      desiredBoolValue: desiredBoolValue,
      nextFlushAt: DateTime.now().add(config.flushDelay),
    );
    final nextEntries = List<ClientStateSyncOutboxEntry>.from(state.entries)
      ..removeWhere((item) => item.coalesceKey == coalesceKey)
      ..add(entry);
    state = state.copyWith(entries: nextEntries);
    _scheduleNextFlush();
  }

  void _scheduleNextFlush() {
    _flushTimer?.cancel();
    if (state.entries.isEmpty) return;
    final nextFlushAt = state.entries
        .map((entry) => entry.nextFlushAt)
        .reduce((a, b) => a.isBefore(b) ? a : b);
    final delay = nextFlushAt.difference(DateTime.now());
    _flushTimer = Timer(delay.isNegative ? Duration.zero : delay, () {
      flushNow();
    });
  }
}

final userRelationshipStateProvider =
    NotifierProvider<UserRelationshipStateNotifier, UserRelationshipState>(
      UserRelationshipStateNotifier.new,
    );

final postInteractionStateProvider =
    NotifierProvider<PostInteractionStateNotifier, PostInteractionState>(
      PostInteractionStateNotifier.new,
    );

final clientStateSyncOutboxProvider =
    NotifierProvider<ClientStateSyncOutboxNotifier, ClientStateSyncOutboxState>(
      ClientStateSyncOutboxNotifier.new,
    );

final assistantRepositoryProvider = Provider<AssistantRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteAssistantRepository();
  }
  return MockAssistantRepository();
});

final personalContentAccessProvider =
    NotifierProvider<PersonalContentAccessNotifier, PersonalContentAccessState>(
      PersonalContentAccessNotifier.new,
    );

final assistantPersonalContentAccessGrantedProvider = Provider<bool>((ref) {
  return ref.watch(personalContentAccessProvider).granted;
});

final assistantContentIdentityIndexEnabledProvider = Provider<bool>((ref) {
  final consentGranted = ref.watch(
    assistantPersonalContentAccessGrantedProvider,
  );
  final featureFlag = ref.watch(
    contentFeatureFlagProvider('enable_assistant_content_identity_index'),
  );
  return consentGranted && featureFlag;
});

/// Content Repository（按业务对象组织的端侧入口）
final contentRepositoryProvider = Provider<ContentRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteContentRepository();
  }
  return MockContentRepository();
});

/// Homepage Repository（共享主页搜索、详情、认领与治理）
final homepageRepositoryProvider = Provider<HomepageRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteHomepageRepository()
      : MockHomepageRepository();
});

/// Chat Repository（按业务对象组织的端侧入口）
final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteChatRepository();
  }
  return MockChatRepository();
});

/// 会话缓存（LRU 内存 200 条 + 磁盘持久化无 TTL）
final conversationCacheProvider = Provider<ConversationCacheService>((ref) {
  return ConversationCacheService();
});

/// 用户资料缓存（LRU 内存 200 条 + 磁盘持久化无 TTL）
final userProfileCacheProvider = Provider<UserProfileCacheService>((ref) {
  return UserProfileCacheService();
});

/// 会话同步引擎
final conversationSyncProvider = Provider<ConversationSyncService>((ref) {
  return ConversationSyncService(
    repo: ref.watch(chatRepositoryProvider),
    cache: ref.watch(conversationCacheProvider),
  );
});

/// User Repository（按业务对象组织的端侧入口）
final userRepositoryProvider = Provider<UserRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteUserRepository();
  }
  return MockUserRepository();
});

/// 当前活动分身上下文。mock 模式下允许回退；remote 模式由调用方自行决定是否 fail-closed。
final activePersonaContextProvider =
    FutureProvider<ActivePersonaContextViewData>((ref) async {
      try {
        return await ref.read(userRepositoryProvider).getActivePersonaContext();
      } catch (_) {
        final currentUser = ref.read(userDataProvider);
        final fallbackId = currentUser?.id.isNotEmpty == true
            ? currentUser!.id
            : ref.read(currentUserIdProvider);
        return ActivePersonaContextViewData.fallback(
          profileSubjectId: fallbackId,
          ownerUserId:
              currentUser?.metadata?['ownerUserId']?.toString() ?? fallbackId,
          subAccountId:
              currentUser?.metadata?['subAccountId']?.toString() ?? '',
          subjectType:
              currentUser?.metadata?['subjectType']?.toString() ?? 'owner',
          displayName:
              currentUser?.displayName ?? currentUser?.username ?? fallbackId,
          avatarUrl: currentUser?.avatarUrlOrAvatar ?? '',
          personaContextVersion:
              currentUser?.metadata?['personaContextVersion']?.toString() ?? '',
        );
      }
    });

/// Auth Repository（登录/凭证/子账号管理）
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteAuthRepository();
  }
  return MockAuthRepository();
});

/// Invite Repository（邀请归因）
final inviteRepositoryProvider = Provider<InviteRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteInviteRepository();
  }
  return MockInviteRepository();
});

/// Behavior Repository（行为上报，驱动实时推荐）
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteBehaviorRepository();
  }
  return MockBehaviorRepository();
});

/// UserProfile Repository（用户主页：帖子 / 作品集 / 生活记录）
final userProfileRepositoryProvider = Provider<UserProfileRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteUserProfileRepository()
      : const MockUserProfileRepository();
});

/// ContentInteraction Repository（like/unlike/favorite/unfavorite）
final contentInteractionRepositoryProvider =
    Provider<ContentInteractionRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return mode == AppDataSourceMode.remote
          ? RemoteContentInteractionRepository()
          : MockContentInteractionRepository();
    });

/// Block Repository（拉黑/取消拉黑用户）
final blockRepositoryProvider = Provider<BlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteBlockRepository()
      : MockBlockRepository();
});

/// Report Repository（内容举报）
final reportRepositoryProvider = Provider<ReportRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteReportRepository()
      : MockReportRepository();
});

/// KeywordBlock Repository（屏蔽词设置）
final keywordBlockRepositoryProvider = Provider<KeywordBlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteKeywordBlockRepository()
      : MockKeywordBlockRepository();
});

/// Circle Repository（圈子管理、成员、存储、Feed）
final circleRepositoryProvider = Provider<CircleRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteCircleRepository()
      : MockCircleRepository();
});

/// RTC Repository（实时通话：发起、接听、挂断、录制等）
final rtcRepositoryProvider = Provider<RtcRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteRtcRepository()
      : MockRtcRepository();
});

/// RelationshipCapability Repository（关系能力位投影，用户主页五态按钮矩阵 + RTC 门禁）
final relationshipCapabilityRepositoryProvider =
    Provider<RelationshipCapabilityRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return mode == AppDataSourceMode.remote
          ? RemoteRelationshipCapabilityRepository()
          : MockRelationshipCapabilityRepository();
    });

/// CallSettings Repository（来电铃声与响铃偏好）
final callSettingsRepositoryProvider = Provider<CallSettingsRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteCallSettingsRepository()
      : MockCallSettingsRepository();
});

/// AppearanceSettings Repository（外观与字号偏好）
final appearanceSettingsRepositoryProvider =
    Provider<AppearanceSettingsRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return mode == AppDataSourceMode.remote
          ? RemoteAppearanceSettingsRepository()
          : MockAppearanceSettingsRepository();
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteGreetingRepository()
      : MockGreetingRepository();
});

/// Media Upload Manager（统一媒体上传队列 + 并发 + 重试 + 离线恢复）
final mediaUploadManagerProvider = Provider<MediaUploadManager>((ref) {
  final manager = MediaUploadManager();
  manager.startOfflineMonitor();
  ref.onDispose(manager.dispose);
  return manager;
});

/// Media Download Cache（LRU 媒体下载缓存，默认 200MB）
final mediaDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  return MediaDownloadCache();
});
