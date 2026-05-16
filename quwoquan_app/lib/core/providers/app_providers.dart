import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_interaction_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_repository.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_repository.dart';
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
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/client_state_sync.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/conversation_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/di/cloud_repository_binding.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
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
      final avatarUrl = profile.avatarUrl.isNotEmpty ? profile.avatarUrl : null;
      final subAccountId = profile.subAccountId.isNotEmpty
          ? profile.subAccountId
          : userId;
      state = User(
        id: subAccountId,
        username: profile.username.isNotEmpty ? profile.username : userId,
        displayName: profile.displayName.isNotEmpty
            ? profile.displayName
            : null,
        avatarUrl: avatarUrl,
        avatar: avatarUrl,
        bio: profile.bio.isNotEmpty ? profile.bio : null,
        backgroundImage: profile.backgroundUrl.isNotEmpty
            ? profile.backgroundUrl
            : null,
        metadata: <String, dynamic>{
          'ownerUserId': profile.ownerUserId,
          'subAccountId': profile.subAccountId,
          'subjectType': profile.subjectType,
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

/// 当前用户 ID — 以 User 快照为准；环境包可显式注入测试/预置用户。
final currentUserIdProvider = Provider<String>((ref) {
  final profileUserId = ref.watch(userDataProvider)?.id;
  if (profileUserId != null && profileUserId.isNotEmpty) {
    return profileUserId;
  }
  return const String.fromEnvironment('APP_CURRENT_USER_ID');
});

/// 当前请求归属的 owner user id。
///
/// 优先使用已加载用户快照里的 `ownerUserId`，否则回退到当前用户 id，
/// 避免 remote 读链路在分身上下文尚未就绪时完全拿不到 `X-Client-User-Id`。
final resolvedOwnerUserIdProvider = Provider<String>((ref) {
  final currentUser = ref.watch(userDataProvider);
  final ownerUserId =
      currentUser?.metadata?['ownerUserId']?.toString().trim() ?? '';
  if (ownerUserId.isNotEmpty) {
    return ownerUserId;
  }
  return ref.watch(currentUserIdProvider).trim();
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

final opsVisitRepositoryProvider = Provider<OpsVisitRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteOpsVisitRepository();
  }
  return MockOpsVisitRepository();
});

final opsEventRepositoryProvider = Provider<OpsEventRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteOpsEventRepository();
  }
  return MockOpsEventRepository();
});

/// 浏览记录服务 Provider（小趣基线：记录访问用于 experienceLevel）
final visitRecorderServiceProvider = Provider<VisitRecorderService>((ref) {
  return VisitRecorderService(
    remoteRepository: ref.watch(opsVisitRepositoryProvider),
    currentUserId: ref.watch(currentUserIdProvider),
  );
});

const Map<String, bool> _contentStoryBootstrapFlags = <String, bool>{
  'enable_create_action_entry': true,
  'enable_unified_create_editor': true,
  'simple_create_action_sheet': true,
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
        errorMessage: runtimeErrorDisplayMessage(error),
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
      state = state.copyWith(
        isSyncing: false,
        errorMessage: runtimeErrorDisplayMessage(error),
      );
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
    return ContentRuntimeConfigState.fromClientParsed(
      ContentAppConfigClientParsed.fromRootMap(config),
      fallback: fallback,
    );
  }

  factory ContentRuntimeConfigState.fromClientParsed(
    ContentAppConfigClientParsed parsed, {
    required ContentRuntimeConfigState fallback,
  }) {
    final mergedFlags = <String, bool>{
      ...fallback.featureFlags,
      ...parsed.featureFlagOverrides,
    };
    final gray = parsed.grayRelease;
    final rawStages = gray.canaryMatrix
        .map(
          (w) => ContentCanaryStage(
            stage: w.stage,
            rolloutPercent: w.rolloutPercent,
          ),
        )
        .toList(growable: false);
    final experimentBucket = gray.experimentBucket.trim();
    final currentCanaryStage = gray.currentStage.trim();
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
        parsed.clientStateSyncMap,
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
      state = ContentRuntimeConfigState.fromClientParsed(
        remoteConfig.clientParsed,
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

const String _personaManagementFeatureFlag = 'ops.user.persona_management_v1';
const String _personaProfileSyncFeatureFlag =
    'ops.user.persona_profile_sync_v1';

bool _runtimeFlagOrEnabledDefault(Ref ref, String flag) {
  final config = ref.watch(contentRuntimeConfigProvider);
  if (config.featureFlags.containsKey(flag)) {
    return config.isEnabled(flag);
  }
  return true;
}

const String _clientInteractionStateBoxName = 'client_interaction_state';
const String _userRelationshipStateStorageKey = 'user_relationship_state_v1';
const String _postInteractionStateStorageKey = 'post_interaction_state_v1';
const String _clientStateSyncOutboxStorageKey = 'client_state_sync_outbox_v1';

Future<Box<String>> _ensureClientInteractionStateBox() async {
  if (!Hive.isBoxOpen(_clientInteractionStateBoxName)) {
    try {
      await Hive.initFlutter();
    } catch (_) {}
    return Hive.openBox<String>(_clientInteractionStateBoxName);
  }
  return Hive.box<String>(_clientInteractionStateBoxName);
}

Future<Map<String, dynamic>?> _readPersistedInteractionMap(String key) async {
  try {
    final box = await _ensureClientInteractionStateBox();
    final raw = box.get(key);
    if (raw == null || raw.isEmpty) {
      return null;
    }
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    if (decoded is Map) {
      return decoded.cast<String, dynamic>();
    }
  } catch (_) {}
  return null;
}

Future<void> _writePersistedInteractionMap(
  String key,
  Map<String, dynamic> value,
) async {
  try {
    final box = await _ensureClientInteractionStateBox();
    await box.put(key, jsonEncode(value));
  } catch (_) {}
}

final personaManagementFeatureFlagProvider = Provider<bool>((ref) {
  return _runtimeFlagOrEnabledDefault(ref, _personaManagementFeatureFlag);
});

final personaProfileSyncFeatureFlagProvider = Provider<bool>((ref) {
  return ref.watch(personaManagementFeatureFlagProvider) &&
      _runtimeFlagOrEnabledDefault(ref, _personaProfileSyncFeatureFlag);
});

class UserRelationshipState {
  const UserRelationshipState({
    this.followingSubAccountIds = const <String>{},
    this.knownSubAccountIds = const <String>{},
  });

  final Set<String> followingSubAccountIds;
  final Set<String> knownSubAccountIds;

  bool isFollowing(String subAccountId) {
    return followingSubAccountIds.contains(subAccountId);
  }

  bool hasRelationshipStateFor(String subAccountId) {
    return knownSubAccountIds.contains(subAccountId);
  }

  UserRelationshipState copyWith({
    Set<String>? followingSubAccountIds,
    Set<String>? knownSubAccountIds,
  }) {
    return UserRelationshipState(
      followingSubAccountIds:
          followingSubAccountIds ?? this.followingSubAccountIds,
      knownSubAccountIds: knownSubAccountIds ?? this.knownSubAccountIds,
    );
  }

  factory UserRelationshipState.fromMap(Map<String, dynamic> map) {
    Set<String> readSet(String key) {
      final raw = map[key];
      if (raw is List) {
        return raw.map((item) => item.toString()).toSet();
      }
      return const <String>{};
    }

    final following = readSet('followingSubAccountIds');
    final known = readSet('knownSubAccountIds');
    return UserRelationshipState(
      followingSubAccountIds: following,
      knownSubAccountIds: known.isEmpty ? following : known,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'followingSubAccountIds':
          followingSubAccountIds.toList(growable: false),
      'knownSubAccountIds': knownSubAccountIds.toList(growable: false),
    };
  }
}

class UserRelationshipStateNotifier extends Notifier<UserRelationshipState> {
  @override
  UserRelationshipState build() {
    unawaited(_hydratePersistedState());
    return const UserRelationshipState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await _readPersistedInteractionMap(
      _userRelationshipStateStorageKey,
    );
    if (raw == null) {
      return;
    }
    state = UserRelationshipState.fromMap(raw);
  }

  void seedFollowing(
    Iterable<String> subAccountIds, {
    Iterable<String>? knownSubAccountIds,
  }) {
    state = UserRelationshipState(
      followingSubAccountIds: Set<String>.from(subAccountIds),
      knownSubAccountIds: Set<String>.from(
        knownSubAccountIds ?? subAccountIds,
      ),
    );
    unawaited(_persistState());
  }

  void setFollowing(String subAccountId, bool isFollowing) {
    final next = Set<String>.from(state.followingSubAccountIds);
    final nextKnown = Set<String>.from(state.knownSubAccountIds)
      ..add(subAccountId);
    if (isFollowing) {
      next.add(subAccountId);
    } else {
      next.remove(subAccountId);
    }
    state = state.copyWith(
      followingSubAccountIds: next,
      knownSubAccountIds: nextKnown,
    );
    unawaited(_persistState());
  }

  void mergeInteractionSnapshot(MediaViewerInteractionSnapshot snapshot) {
    final scopeProfileIds = snapshot.effectiveScopeProfileIds;
    if (scopeProfileIds.isEmpty && snapshot.followingUsers.isEmpty) {
      return;
    }
    final effectiveScope = scopeProfileIds.isEmpty
        ? snapshot.followingUsers
        : scopeProfileIds;
    final nextFollowing = Set<String>.from(state.followingSubAccountIds);
    final nextKnown = Set<String>.from(state.knownSubAccountIds)
      ..addAll(effectiveScope);
    for (final profileId in effectiveScope) {
      if (snapshot.followingUsers.contains(profileId)) {
        nextFollowing.add(profileId);
      } else {
        nextFollowing.remove(profileId);
      }
    }
    state = state.copyWith(
      followingSubAccountIds: nextFollowing,
      knownSubAccountIds: nextKnown,
    );
    unawaited(_persistState());
  }

  void applyViewerResult(MediaViewerResult result) {
    mergeInteractionSnapshot(result);
  }

  Future<void> _persistState() async {
    await _writePersistedInteractionMap(
      _userRelationshipStateStorageKey,
      state.toMap(),
    );
  }
}

class PostInteractionState {
  const PostInteractionState({
    this.likedPostIds = const <String>{},
    this.savedPostIds = const <String>{},
    this.sharedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.bookmarkCounts = const <String, int>{},
    this.confirmedShareCounts = const <String, int>{},
    this.pendingShareDeltas = const <String, int>{},
    this.confirmedCommentCounts = const <String, int>{},
    this.pendingCommentDeltas = const <String, int>{},
  });

  final Set<String> likedPostIds;
  final Set<String> savedPostIds;
  final Set<String> sharedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> bookmarkCounts;
  final Map<String, int> confirmedShareCounts;
  final Map<String, int> pendingShareDeltas;
  final Map<String, int> confirmedCommentCounts;
  final Map<String, int> pendingCommentDeltas;

  bool isLiked(String postId) => likedPostIds.contains(postId);
  bool isSaved(String postId) => savedPostIds.contains(postId);
  bool isShared(String postId) => sharedPostIds.contains(postId);

  bool hasLikeStateFor(String postId) {
    return likedPostIds.contains(postId) || likeCounts.containsKey(postId);
  }

  bool hasSaveStateFor(String postId) {
    return savedPostIds.contains(postId) || bookmarkCounts.containsKey(postId);
  }

  int likeCountFor(String postId, {int fallback = 0}) {
    return likeCounts[postId] ?? fallback;
  }

  int bookmarkCountFor(String postId, {int fallback = 0}) {
    return bookmarkCounts[postId] ?? fallback;
  }

  int shareCountFor(String postId, {int fallback = 0}) {
    final confirmed = confirmedShareCounts[postId] ?? fallback;
    final pending = pendingShareDeltas[postId] ?? 0;
    return math.max(0, confirmed + pending);
  }

  int commentCountFor(String postId, {int fallback = 0}) {
    final confirmed = confirmedCommentCounts[postId] ?? fallback;
    final pending = pendingCommentDeltas[postId] ?? 0;
    return math.max(0, confirmed + pending);
  }

  PostInteractionState copyWith({
    Set<String>? likedPostIds,
    Set<String>? savedPostIds,
    Set<String>? sharedPostIds,
    Map<String, int>? likeCounts,
    Map<String, int>? bookmarkCounts,
    Map<String, int>? confirmedShareCounts,
    Map<String, int>? pendingShareDeltas,
    Map<String, int>? confirmedCommentCounts,
    Map<String, int>? pendingCommentDeltas,
  }) {
    return PostInteractionState(
      likedPostIds: likedPostIds ?? this.likedPostIds,
      savedPostIds: savedPostIds ?? this.savedPostIds,
      sharedPostIds: sharedPostIds ?? this.sharedPostIds,
      likeCounts: likeCounts ?? this.likeCounts,
      bookmarkCounts: bookmarkCounts ?? this.bookmarkCounts,
      confirmedShareCounts: confirmedShareCounts ?? this.confirmedShareCounts,
      pendingShareDeltas: pendingShareDeltas ?? this.pendingShareDeltas,
      confirmedCommentCounts:
          confirmedCommentCounts ?? this.confirmedCommentCounts,
      pendingCommentDeltas: pendingCommentDeltas ?? this.pendingCommentDeltas,
    );
  }

  factory PostInteractionState.fromMap(Map<String, dynamic> map) {
    Set<String> readSet(String key) {
      final raw = map[key];
      if (raw is List) {
        return raw.map((item) => item.toString()).toSet();
      }
      return const <String>{};
    }

    Map<String, int> readIntMap(String key) {
      final raw = map[key];
      if (raw is Map) {
        return raw.map(
          (entryKey, value) => MapEntry(
            entryKey.toString(),
            value is num ? value.toInt() : int.tryParse(value.toString()) ?? 0,
          ),
        );
      }
      return const <String, int>{};
    }

    return PostInteractionState(
      likedPostIds: readSet('likedPostIds'),
      savedPostIds: readSet('savedPostIds'),
      sharedPostIds: readSet('sharedPostIds'),
      likeCounts: readIntMap('likeCounts'),
      bookmarkCounts: readIntMap('bookmarkCounts'),
      confirmedShareCounts: readIntMap('confirmedShareCounts').isNotEmpty
          ? readIntMap('confirmedShareCounts')
          : readIntMap('shareCounts'),
      pendingShareDeltas: readIntMap('pendingShareDeltas'),
      confirmedCommentCounts: readIntMap('confirmedCommentCounts').isNotEmpty
          ? readIntMap('confirmedCommentCounts')
          : readIntMap('commentCounts'),
      pendingCommentDeltas: readIntMap('pendingCommentDeltas'),
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'likedPostIds': likedPostIds.toList(growable: false),
      'savedPostIds': savedPostIds.toList(growable: false),
      'sharedPostIds': sharedPostIds.toList(growable: false),
      'likeCounts': likeCounts,
      'bookmarkCounts': bookmarkCounts,
      'confirmedShareCounts': confirmedShareCounts,
      'pendingShareDeltas': pendingShareDeltas,
      'confirmedCommentCounts': confirmedCommentCounts,
      'pendingCommentDeltas': pendingCommentDeltas,
    };
  }
}

class PostInteractionStateNotifier extends Notifier<PostInteractionState> {
  @override
  PostInteractionState build() {
    unawaited(_hydratePersistedState());
    return const PostInteractionState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await _readPersistedInteractionMap(
      _postInteractionStateStorageKey,
    );
    if (raw == null) {
      return;
    }
    state = PostInteractionState.fromMap(raw);
  }

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
    unawaited(_persistState());
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
    unawaited(_persistState());
  }

  void setShared(String postId, bool isShared) {
    final nextShared = Set<String>.from(state.sharedPostIds);
    if (isShared) {
      nextShared.add(postId);
    } else {
      nextShared.remove(postId);
    }
    state = state.copyWith(sharedPostIds: nextShared);
    unawaited(_persistState());
  }

  void applyConfirmedCounters(
    String postId, {
    int? shareCount,
    int? commentCount,
  }) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextPendingShareDeltas = Map<String, int>.from(
      state.pendingShareDeltas,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    if (shareCount != null) {
      nextConfirmedShareCounts[postId] = shareCount;
      nextPendingShareDeltas.remove(postId);
    }
    if (commentCount != null) {
      nextConfirmedCommentCounts[postId] = commentCount;
      nextPendingCommentDeltas.remove(postId);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      pendingShareDeltas: nextPendingShareDeltas,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void setShareCount(String postId, int shareCount) {
    applyConfirmedCounters(postId, shareCount: shareCount);
  }

  void setCommentCount(String postId, int commentCount) {
    applyConfirmedCounters(postId, commentCount: commentCount);
  }

  void applyConfirmedPosts(Iterable<PostBaseDto> posts) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextPendingShareDeltas = Map<String, int>.from(
      state.pendingShareDeltas,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final post in posts) {
      if (post.id.trim().isEmpty) {
        continue;
      }
      nextConfirmedShareCounts[post.id] = post.shareCount;
      nextPendingShareDeltas.remove(post.id);
      nextConfirmedCommentCounts[post.id] = post.commentCount;
      nextPendingCommentDeltas.remove(post.id);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      pendingShareDeltas: nextPendingShareDeltas,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void stageOptimisticShare(
    String postId, {
    required int baseShareCount,
    int delta = 1,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedShareCounts);
    final nextPending = Map<String, int>.from(state.pendingShareDeltas);
    final nextShared = Set<String>.from(state.sharedPostIds);
    nextConfirmed.putIfAbsent(postId, () => baseShareCount);
    nextPending[postId] = (nextPending[postId] ?? 0) + delta;
    nextShared.add(postId);
    state = state.copyWith(
      sharedPostIds: nextShared,
      confirmedShareCounts: nextConfirmed,
      pendingShareDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void rollbackOptimisticShare(
    String postId, {
    required int baseShareCount,
    int delta = 1,
    bool isShared = false,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedShareCounts);
    final nextPending = Map<String, int>.from(state.pendingShareDeltas);
    final nextShared = Set<String>.from(state.sharedPostIds);
    nextConfirmed.putIfAbsent(postId, () => baseShareCount);
    final reverted = (nextPending[postId] ?? 0) - delta;
    if (reverted == 0) {
      nextPending.remove(postId);
    } else {
      nextPending[postId] = reverted;
    }
    if (isShared) {
      nextShared.add(postId);
    } else {
      nextShared.remove(postId);
    }
    state = state.copyWith(
      sharedPostIds: nextShared,
      confirmedShareCounts: nextConfirmed,
      pendingShareDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void stageOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    nextPending[postId] = (nextPending[postId] ?? 0) + delta;
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void rollbackOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    final reverted = (nextPending[postId] ?? 0) - delta;
    if (reverted == 0) {
      nextPending.remove(postId);
    } else {
      nextPending[postId] = reverted;
    }
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void mergeInteractionSnapshot(MediaViewerInteractionSnapshot snapshot) {
    final scopePostIds = snapshot.effectiveScopePostIds;
    if (scopePostIds.isEmpty) {
      return;
    }
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextSaved = Set<String>.from(state.savedPostIds);
    final nextLikeCounts = Map<String, int>.from(state.likeCounts);
    final nextBookmarkCounts = Map<String, int>.from(state.bookmarkCounts);
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextPendingShareDeltas = Map<String, int>.from(
      state.pendingShareDeltas,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final postId in scopePostIds) {
      if (snapshot.likedPosts.contains(postId)) {
        nextLiked.add(postId);
      } else {
        nextLiked.remove(postId);
      }
      if (snapshot.savedPosts.contains(postId)) {
        nextSaved.add(postId);
      } else {
        nextSaved.remove(postId);
      }
      final likeCount = snapshot.postLikesCount[postId];
      if (likeCount != null) {
        nextLikeCounts[postId] = likeCount;
      }
      final bookmarkCount = snapshot.postBookmarksCount[postId];
      if (bookmarkCount != null) {
        nextBookmarkCounts[postId] = bookmarkCount;
      }
      final shareCount = snapshot.postSharesCount[postId];
      if (shareCount != null) {
        nextConfirmedShareCounts[postId] = shareCount;
        nextPendingShareDeltas.remove(postId);
      }
      final commentCount = snapshot.postCommentCount[postId];
      if (commentCount != null) {
        nextConfirmedCommentCounts[postId] = commentCount;
        nextPendingCommentDeltas.remove(postId);
      }
    }
    state = state.copyWith(
      likedPostIds: nextLiked,
      savedPostIds: nextSaved,
      likeCounts: nextLikeCounts,
      bookmarkCounts: nextBookmarkCounts,
      confirmedShareCounts: nextConfirmedShareCounts,
      pendingShareDeltas: nextPendingShareDeltas,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void applyViewerResult(MediaViewerResult result) {
    mergeInteractionSnapshot(result);
  }

  Future<void> _persistState() async {
    await _writePersistedInteractionMap(
      _postInteractionStateStorageKey,
      state.toMap(),
    );
  }
}

class ClientStateSyncOutboxNotifier
    extends Notifier<ClientStateSyncOutboxState> {
  Timer? _flushTimer;

  @override
  ClientStateSyncOutboxState build() {
    unawaited(_hydratePersistedState());
    ref.onDispose(() {
      _flushTimer?.cancel();
    });
    return const ClientStateSyncOutboxState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await _readPersistedInteractionMap(
      _clientStateSyncOutboxStorageKey,
    );
    if (raw == null) {
      return;
    }
    state = ClientStateSyncOutboxState.fromMap(raw);
    _scheduleNextFlush();
  }

  void enqueueFollow({
    required String subAccountId,
    required bool shouldFollow,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: subAccountId,
      intentType: 'follow',
      desiredBoolValue: shouldFollow,
      flushImmediately: flushImmediately,
    );
  }

  void enqueuePostLike({
    required String postId,
    required bool isLiked,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'like',
      desiredBoolValue: isLiked,
      flushImmediately: flushImmediately,
    );
  }

  void enqueuePostSave({
    required String postId,
    required bool isSaved,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'save',
      desiredBoolValue: isSaved,
      flushImmediately: flushImmediately,
    );
  }

  void enqueuePostShare({
    required String postId,
    required bool isShared,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'share',
      desiredBoolValue: isShared,
      flushImmediately: flushImmediately,
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
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  Future<void> _flushEntry(ClientStateSyncOutboxEntry entry) async {
    switch ('${entry.objectType}:${entry.intentType}') {
      case 'profile:follow':
        final repo = ref.read(userProfileRepositoryProvider);
        final activeContext = await ref.read(
          activePersonaContextProvider.future,
        );
        if (entry.desiredBoolValue) {
          await repo.followUser(
            entry.objectId,
            ownerUserId: activeContext.ownerUserId,
            subAccountId: activeContext.subAccountId,
            subAccountContextVersion: activeContext.contextVersion,
          );
        } else {
          await repo.unfollowUser(
            entry.objectId,
            ownerUserId: activeContext.ownerUserId,
            subAccountId: activeContext.subAccountId,
            subAccountContextVersion: activeContext.contextVersion,
          );
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
      case 'post:share':
        final repo = ref.read(contentRepositoryProvider);
        if (entry.desiredBoolValue) {
          await repo.sharePost(postId: entry.objectId);
        } else {
          await repo.unsharePost(postId: entry.objectId);
        }
        return;
    }
  }

  void _upsertEntry({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool desiredBoolValue,
    required bool flushImmediately,
  }) {
    final config = ref.read(contentRuntimeConfigProvider).clientStateSync;
    final now = DateTime.now();
    final coalesceKey = '$objectType:$intentType:$objectId';
    final entry = ClientStateSyncOutboxEntry(
      coalesceKey: coalesceKey,
      objectType: objectType,
      objectId: objectId,
      intentType: intentType,
      desiredBoolValue: desiredBoolValue,
      nextFlushAt: flushImmediately ? now : now.add(config.flushDelay),
    );
    final nextEntries = List<ClientStateSyncOutboxEntry>.from(state.entries)
      ..removeWhere((item) => item.coalesceKey == coalesceKey)
      ..add(entry);
    state = state.copyWith(entries: nextEntries);
    unawaited(_persistState());
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

  Future<void> _persistState() async {
    await _writePersistedInteractionMap(
      _clientStateSyncOutboxStorageKey,
      state.toMap(),
    );
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
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteAssistantRepository.new,
    mock: MockAssistantRepository.new,
  );
});

final appMessageRepositoryProvider = Provider<AppMessageRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteAppMessageRepository.new,
    mock: MockAppMessageRepository.new,
  );
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
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteContentRepository.new,
    mock: MockContentRepository.new,
  );
});

/// Homepage Repository（共享主页搜索、详情、认领与治理）
final homepageRepositoryProvider = Provider<HomepageRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteHomepageRepository.new,
    mock: MockHomepageRepository.new,
  );
});

/// Integration Repository（外部能力集成：位置 nearby / search）
final integrationRepositoryProvider = Provider<IntegrationRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteIntegrationRepository.new,
    mock: () => const MockIntegrationRepository(),
  );
});

/// Chat Repository（按业务对象组织的端侧入口）
final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteChatRepository(
      mergeRequestContext: (base) async {
        final ctx = ref.read(activePersonaContextProvider).asData?.value;
        final resolvedOwnerUserId = ctx?.ownerUserId.trim() ?? '';
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: resolvedOwnerUserId.isNotEmpty
              ? resolvedOwnerUserId
              : ownerUserId,
          subAccountId: ctx?.subAccountId ?? '',
          subAccountContextVersion: ctx?.personaContextVersion ?? '',
        );
      },
    ),
    mock: MockChatRepository.new,
  );
});

/// 会话缓存（按 namespace 隔离，支持列表增量监听）
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
    userSyncRepository: ref.watch(userSyncRepositoryProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.read(activePersonaContextLoaderProvider),
  );
});

final localChatSearchStoreProvider = Provider<LocalChatSearchStore>((ref) {
  return LocalChatSearchStore.shared;
});

final localCircleGroupSnapshotStoreProvider =
    Provider<LocalCircleGroupSnapshotStore>((ref) {
      return LocalCircleGroupSnapshotStore.shared;
    });

/// User Repository（按业务对象组织的端侧入口）
final userRepositoryProvider = Provider<UserRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteUserRepository(
      mergeRequestContext: (base) async {
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: ownerUserId,
        );
      },
    ),
    mock: MockUserRepository.new,
  );
});

final userSyncRepositoryProvider = Provider<UserSyncRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteUserSyncRepository(
      mergeRequestContext: (base) async {
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: ownerUserId,
        );
      },
    ),
    mock: MockUserSyncRepository.new,
  );
});

/// 当前活动分身上下文。只有 mock 模式允许本地回退；remote 模式必须显式失败，避免关键写路径静默降级到 user。
final activePersonaContextProvider =
    FutureProvider<ActivePersonaContextViewData>((ref) async {
      final mode = ref.read(appDataSourceModeProvider);
      try {
        return await ref.read(userRepositoryProvider).getActivePersonaContext();
      } catch (_) {
        if (mode == AppDataSourceMode.remote) {
          rethrow;
        }
        final currentUser = ref.read(userDataProvider);
        final fallbackId = currentUser?.id.isNotEmpty == true
            ? currentUser!.id
            : ref.read(currentUserIdProvider);
        return ActivePersonaContextViewData.fallback(
          subAccountId:
              currentUser?.metadata?['subAccountId']?.toString() ?? fallbackId,
          ownerUserId:
              currentUser?.metadata?['ownerUserId']?.toString() ?? fallbackId,
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
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteAuthRepository.new,
    mock: MockAuthRepository.new,
  );
});

/// Invite Repository（邀请归因）
final inviteRepositoryProvider = Provider<InviteRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteInviteRepository.new,
    mock: MockInviteRepository.new,
  );
});

/// Behavior Repository（行为上报，驱动实时推荐）
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteBehaviorRepository(
      eventRepository: ref.watch(opsEventRepositoryProvider),
      currentUserId: ref.watch(currentUserIdProvider),
      experimentBucket: ref
          .watch(contentRuntimeConfigProvider)
          .experimentBucket,
    );
  }
  return MockBehaviorRepository();
});

/// UserProfile Repository（用户主页：帖子 / 作品集 / 生活记录）
final userProfileRepositoryProvider = Provider<UserProfileRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteUserProfileRepository.new,
    mock: () => const MockUserProfileRepository(),
  );
});

/// ContentInteraction Repository（like/unlike/favorite/unfavorite）
final contentInteractionRepositoryProvider =
    Provider<ContentInteractionRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: RemoteContentInteractionRepository.new,
        mock: MockContentInteractionRepository.new,
      );
    });

/// Block Repository（拉黑/取消拉黑用户）
final blockRepositoryProvider = Provider<BlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteBlockRepository.new,
    mock: MockBlockRepository.new,
  );
});

/// Report Repository（内容举报）
final reportRepositoryProvider = Provider<ReportRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteReportRepository.new,
    mock: MockReportRepository.new,
  );
});

/// KeywordBlock Repository（屏蔽词设置）
final keywordBlockRepositoryProvider = Provider<KeywordBlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteKeywordBlockRepository.new,
    mock: MockKeywordBlockRepository.new,
  );
});

/// Circle Repository（圈子管理、成员、存储、Feed）
final circleRepositoryProvider = Provider<CircleRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteCircleRepository.new,
    mock: MockCircleRepository.new,
  );
});

final activePersonaContextLoaderProvider = Provider<PersonaContextLoader>((
  ref,
) {
  return ref.read(userRepositoryProvider).getActivePersonaContext;
});

final localChatSearchSyncProvider = Provider<LocalChatSearchSyncService>((ref) {
  return LocalChatSearchSyncService(
    chatRepository: ref.watch(chatRepositoryProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
  );
});

final searchRepositoryProvider = Provider<SearchRepository>((ref) {
  return buildAppSearchRepository(
    circleRepository: ref.watch(circleRepositoryProvider),
    contentRepository: ref.watch(contentRepositoryProvider),
    homepageRepository: ref.watch(homepageRepositoryProvider),
    integrationRepository: ref.watch(integrationRepositoryProvider),
    localChatSearchStore: ref.watch(localChatSearchStoreProvider),
    localChatSearchSyncService: ref.watch(localChatSearchSyncProvider),
    localCircleGroupSnapshotStore: ref.watch(
      localCircleGroupSnapshotStoreProvider,
    ),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
  );
});

/// RTC Repository（实时通话：发起、接听、挂断、录制等）
final rtcRepositoryProvider = Provider<RtcRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteRtcRepository.new,
    mock: MockRtcRepository.new,
  );
});

/// RelationshipCapability Repository（关系能力位投影，用户主页五态按钮矩阵 + RTC 门禁）
final relationshipCapabilityRepositoryProvider =
    Provider<RelationshipCapabilityRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: RemoteRelationshipCapabilityRepository.new,
        mock: MockRelationshipCapabilityRepository.new,
      );
    });

/// CallSettings Repository（来电铃声与响铃偏好）
final callSettingsRepositoryProvider = Provider<CallSettingsRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteCallSettingsRepository.new,
    mock: MockCallSettingsRepository.new,
  );
});

/// AppearanceSettings Repository（外观与字号偏好）
final appearanceSettingsRepositoryProvider =
    Provider<AppearanceSettingsRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: RemoteAppearanceSettingsRepository.new,
        mock: MockAppearanceSettingsRepository.new,
      );
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: RemoteGreetingRepository.new,
    mock: MockGreetingRepository.new,
  );
});

/// Tag Repository（标签体系查询、建议、校验与关系图谱）
final tagRepositoryProvider = Provider<TagRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteTagRepository();
  }
  return MockTagRepository();
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
