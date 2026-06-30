import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/home_channels_remote_override.dart';
import 'package:quwoquan_app/cloud/runtime/models/intersection_display_config.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart'
    show AppLogService, AppLogType, AppLogLevel, AppLogContext;
import 'package:quwoquan_app/assistant/observability/logging/app_log_uploader.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
// 发布选点服务（content/entry）。注：实现暂位于 lib/ui/.../services，理想位置应为
// lib/cloud/services/integration（属既有分层债，待用户确认后登记 backlog 再收敛）；
// mode-switch provider 须集中在 core 以满足 verify_ui_app_data_source_mode_ratchet
// （禁止 lib/ui 引用 appDataSourceModeProvider）。
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_repository.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_repository.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/call_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/contact_discovery_repository.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/invite_repository.dart';
import 'package:quwoquan_app/cloud/services/user/keyword_block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/client_state_sync.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/conversation_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_management_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/di/cloud_repository_binding.dart';
import 'package:quwoquan_app/core/services/app_remote_config_store.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/models/user_models.dart';
// 跨平台防腐层 Provider（平台目标、能力契约、文件存储网关、原生桥）统一从
// app_providers 再导出，业务层经同一入口消费能力位，禁止直接判断平台。
export 'package:quwoquan_app/core/platform/platform_providers.dart'
    show
        platformTargetProvider,
        platformCapabilitiesProvider,
        fileStorageGatewayProvider,
        assistantLocalContextBridgeProvider,
        nativeAuthBridgeProvider,
        nativeShareBridgeProvider;

part 'app_providers_content_extras.dart';
part 'app_providers_entity_extras.dart';
part 'app_providers_client_sync.dart';

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
      // 本地选取（相册/拍照）但尚未上传的临时文件路径原样保留（alpha 保存后即时回显），
      // 不经媒体解析器拼成不可访问 URL；服务端对象键 / 远端地址仍正常解析。
      final avatarUrl = isLocalFileImageSource(profile.avatarUrl)
          ? profile.avatarUrl
          : resolveAvatarImageUrl(
              profile.avatarUrl,
              avatarVersion: profile.avatarVersion,
            );
      final backgroundUrl = isLocalFileImageSource(profile.backgroundUrl)
          ? profile.backgroundUrl
          : resolveContentMediaUrl(profile.backgroundUrl);
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
        backgroundImage: backgroundUrl.isNotEmpty ? backgroundUrl : null,
        metadata: <String, dynamic>{
          'ownerUserId': profile.ownerUserId,
          'subAccountId': profile.subAccountId,
          'subjectType': profile.subjectType,
          'avatarVersion': profile.avatarVersion,
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
  final authSession = ref.watch(authSessionControllerProvider);
  if (authSession.activeSubAccountId.isNotEmpty) {
    return authSession.activeSubAccountId;
  }
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
  final authOwnerId = ref.watch(authSessionControllerProvider).ownerId.trim();
  if (authOwnerId.isNotEmpty) {
    return authOwnerId;
  }
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

final appResourceCacheProfileProvider = Provider<AppResourceCacheProfile>((
  ref,
) {
  final responsiveState = ref.watch(responsiveProvider);
  final capabilities = ref.watch(platformCapabilitiesProvider);
  if (!capabilities.wideScreenLayout ||
      responsiveState.breakpoint == AppBreakpoint.compact) {
    return AppResourceCacheProfile.compact;
  }
  if (responsiveState.breakpoint == AppBreakpoint.expanded) {
    return AppResourceCacheProfile.expanded;
  }
  return AppResourceCacheProfile.regular;
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

/// Shared CloudHttpClient with API latency instrumentation.
///
/// All remote repositories should prefer this over constructing their own
/// CloudHttpClient, ensuring every HTTP call is metered for L1 monitoring.
final cloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  return CloudHttpClient(
    authTokenProvider: ProviderBackedCloudAuthTokenProvider(
      () => ref.read(authSessionControllerProvider).accessToken,
    ),
    onUnauthorizedRefresh: () => ref
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(),
    latencyObserver: (method, path, elapsedMs, statusCode) {
      AppLogService.instance.writeEvent(
        logType: AppLogType.perf,
        level: statusCode >= 0 && statusCode < 400
            ? AppLogLevel.info
            : AppLogLevel.warn,
        context: AppLogContext(
          sessionId: AppTraceContextStore.instance.sessionId,
          requestId: AppTraceContextStore.instance.newRequestId(),
          target: 'cloud_api',
          action: '$method $path',
        ),
        payload: <String, dynamic>{
          'kind': 'api_latency',
          'method': method,
          'path': path,
          'elapsedMs': elapsedMs,
          'statusCode': statusCode,
        },
      );
    },
  );
});

final opsVisitRepositoryProvider = Provider<OpsVisitRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteOpsVisitRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    );
  }
  return MockOpsVisitRepository();
});

final opsEventRepositoryProvider = Provider<OpsEventRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    final repo = RemoteOpsEventRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    );
    ref.onDispose(repo.dispose);
    return repo;
  }
  return MockOpsEventRepository();
});

/// 发布选点服务：按数据源模式在 Mock/Remote 间切换。
///
/// - mock（alpha/开发）→ [MockCreateLocationService]：本地 canonical POI，不发 HTTP、
///   不依赖系统定位，杜绝「附近地点访问失败」整页断点。
/// - remote（beta/gamma/prod）→ [RemoteCreateLocationService]：经 gateway/API + 系统定位。
final createLocationServiceProvider = Provider<CreateLocationService>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteCreateLocationService(
      httpClient: ref.watch(cloudHttpClientProvider),
    );
  }
  return MockCreateLocationService();
});

/// AppLog 上传服务 — 定期将本地 ndjson 日志批量上传到 OpsEvent 后端。
final appLogUploaderProvider = Provider<AppLogUploader>((ref) {
  final uploader = AppLogUploader(
    eventRepository: ref.watch(opsEventRepositoryProvider),
  );
  uploader.start();
  ref.onDispose(uploader.dispose);
  return uploader;
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
  'enable_article_book_reader': true,
  'enable_article_page_curl': true,
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
    required this.comment,
    required this.configHash,
    required this.packageVersion,
    required this.source,
    this.homeChannels = ContentUIConfig.homeChannels,
    this.intersectionDisplay = IntersectionDisplayConfig.fallback,
  });

  final Map<String, bool> featureFlags;
  final String experimentBucket;
  final String currentCanaryStage;
  final List<ContentCanaryStage> canaryStages;
  final ClientStateSyncConfig clientStateSync;
  final CommentRemoteConfig comment;
  final String configHash;
  final String packageVersion;
  final AppRemoteConfigSource source;

  /// 首页频道（运营资产）：端默认 [ContentUIConfig.homeChannels]，远程整体覆盖、失败回退默认。
  final List<HomeChannelConfig> homeChannels;

  /// 交集展示控制（就地展开行数 / 推荐候选窗），来自 /v1/config/app，失败回退默认。
  final IntersectionDisplayConfig intersectionDisplay;

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
      comment: CommentRemoteConfig.fallback,
      configHash: AppRemoteConfigSnapshot.fallbackPackageVersion,
      packageVersion: AppRemoteConfigSnapshot.fallbackPackageVersion,
      source: AppRemoteConfigSource.defaults,
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
    List<HomeChannelConfig>? homeChannelsOverride,
    IntersectionDisplayConfig? intersectionDisplayOverride,
    CommentRemoteConfig? commentOverride,
    AppRemoteConfigSnapshot? snapshot,
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
      comment: commentOverride ?? fallback.comment,
      configHash: snapshot?.configHash ?? fallback.configHash,
      packageVersion: snapshot?.packageVersion ?? fallback.packageVersion,
      source: snapshot?.source ?? fallback.source,
      homeChannels: homeChannelsOverride ?? fallback.homeChannels,
      intersectionDisplay:
          intersectionDisplayOverride ?? fallback.intersectionDisplay,
    );
  }
}

class AppRemoteConfigState {
  const AppRemoteConfigState({
    required this.active,
    this.pending,
    this.isHydrating = false,
    this.isRefreshing = false,
    this.errorMessage,
  });

  final ContentRuntimeConfigState active;
  final ContentRuntimeConfigState? pending;
  final bool isHydrating;
  final bool isRefreshing;
  final String? errorMessage;

  AppRemoteConfigState copyWith({
    ContentRuntimeConfigState? active,
    ContentRuntimeConfigState? Function()? pending,
    bool? isHydrating,
    bool? isRefreshing,
    String? Function()? errorMessage,
  }) {
    return AppRemoteConfigState(
      active: active ?? this.active,
      pending: pending == null ? this.pending : pending(),
      isHydrating: isHydrating ?? this.isHydrating,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      errorMessage: errorMessage == null ? this.errorMessage : errorMessage(),
    );
  }
}

class AppRemoteConfigNotifier extends Notifier<AppRemoteConfigState> {
  bool _didScheduleHydration = false;
  Future<void>? _inFlightRefresh;

  @override
  AppRemoteConfigState build() {
    final mode = ref.watch(appDataSourceModeProvider);
    final defaults = ContentRuntimeConfigState.defaults(mode: mode);
    if (!_didScheduleHydration) {
      _didScheduleHydration = true;
      Future<void>.microtask(_hydrateThenRefresh);
    }
    return AppRemoteConfigState(active: defaults, isHydrating: true);
  }

  Future<void> refresh() {
    return _inFlightRefresh ??= _refresh().whenComplete(() {
      _inFlightRefresh = null;
    });
  }

  Future<void> _hydrateThenRefresh() async {
    final hydration = _hydrateLkg();
    if (ref.read(appDataSourceModeProvider) != AppDataSourceMode.remote) {
      await hydration;
      return;
    }
    // 远端 fresh config 不应被磁盘缓存读取阻塞，否则 immediate policy
    // 会在启动路径上长期停留在 embedded defaults。
    unawaited(hydration);
    await refresh();
  }

  Future<void> _hydrateLkg() async {
    final snapshot = await const AppRemoteConfigStore().readActiveSnapshot();
    if (!ref.mounted) return;
    if (snapshot == null) {
      state = state.copyWith(isHydrating: false);
      return;
    }
    if (state.active.source != AppRemoteConfigSource.defaults) {
      state = state.copyWith(isHydrating: false);
      return;
    }
    state = state.copyWith(
      active: _stateFromSnapshot(snapshot, fallback: state.active),
      isHydrating: false,
    );
  }

  Future<void> _refresh() async {
    final fallback = ContentRuntimeConfigState.defaults(
      mode: ref.read(appDataSourceModeProvider),
    );
    state = state.copyWith(isRefreshing: true, errorMessage: () => null);
    try {
      final remoteConfig = await ref
          .read(contentRepositoryProvider)
          .getAppConfig();
      if (!ref.mounted) return;
      final snapshot = AppRemoteConfigSnapshot.fromWire(remoteConfig);
      final next = _stateFromSnapshot(snapshot, fallback: fallback);
      state = state.copyWith(
        active: _shouldActivateImmediately(snapshot) ? next : state.active,
        pending: () => _shouldActivateImmediately(snapshot) ? null : next,
        isHydrating: false,
        isRefreshing: false,
      );
      // 当前会话的远程配置生效不应阻塞在 Hive I/O 上；缓存只用于后续启动优化。
      unawaited(const AppRemoteConfigStore().writeActiveSnapshot(snapshot));
    } catch (error) {
      if (!ref.mounted) return;
      state = state.copyWith(
        active: state.active.source == AppRemoteConfigSource.defaults
            ? fallback
            : state.active,
        isHydrating: false,
        isRefreshing: false,
        errorMessage: () => runtimeErrorDisplayMessage(error),
      );
    }
  }

  ContentRuntimeConfigState _stateFromSnapshot(
    AppRemoteConfigSnapshot snapshot, {
    required ContentRuntimeConfigState fallback,
  }) {
    final channelsOverride = HomeChannelsRemoteOverride.fromAppConfigRoot(
      snapshot.wireRoot,
    );
    final intersectionDisplay = IntersectionDisplayConfig.fromAppConfigRoot(
      snapshot.wireRoot,
    );
    final comment = CommentRemoteConfig.fromAppConfigRoot(snapshot.wireRoot);
    return ContentRuntimeConfigState.fromClientParsed(
      snapshot.contentWire.clientParsed,
      fallback: fallback,
      homeChannelsOverride: channelsOverride,
      intersectionDisplayOverride: intersectionDisplay,
      commentOverride: comment,
      snapshot: snapshot,
    );
  }

  bool _shouldActivateImmediately(AppRemoteConfigSnapshot snapshot) {
    return snapshot.activationPolicy['default'] == 'immediate';
  }
}

final appRemoteConfigProvider =
    NotifierProvider<AppRemoteConfigNotifier, AppRemoteConfigState>(
      AppRemoteConfigNotifier.new,
    );

final contentRuntimeConfigProvider = Provider<ContentRuntimeConfigState>((ref) {
  return ref.watch(appRemoteConfigProvider).active;
});

final commentRemoteConfigProvider = Provider<CommentRemoteConfig>((ref) {
  return ref.watch(contentRuntimeConfigProvider).comment;
});

final contentFeatureFlagProvider = Provider.family<bool, String>((ref, flag) {
  return ref.watch(contentRuntimeConfigProvider).isEnabled(flag);
});

/// 首页频道（运营资产）：端默认 [ContentUIConfig.homeChannels] + `/v1/config/app` 远程覆盖，
/// 失败/缺失回退默认；已按 order 升序。UI 通过本 provider 取频道，禁止硬编码频道列表。
/// 交集展示控制（应用骨架级系统配置），来自 /v1/config/app；UI 通过本 provider 取
/// 就地展开行数等，禁止硬编码或塞进交集列表接口。
final intersectionDisplayConfigProvider = Provider<IntersectionDisplayConfig>((
  ref,
) {
  return ref.watch(contentRuntimeConfigProvider).intersectionDisplay;
});

final homeChannelsProvider = Provider<List<HomeChannelConfig>>((ref) {
  return ref.watch(contentRuntimeConfigProvider).homeChannels;
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
    } catch (_) {
      /* best-effort: Hive 可能已被全局初始化，重复初始化抛错可安全忽略，随后直接打开盒子 */
    }
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
  } catch (_) {
    /* best-effort: 本地交互状态损坏时回退到 null，由调用方按未持久化态初始化 */
  }
  return null;
}

Future<void> _writePersistedInteractionMap(
  String key,
  Map<String, dynamic> value,
) async {
  try {
    final box = await _ensureClientInteractionStateBox();
    await box.put(key, jsonEncode(value));
  } catch (_) {
    /* best-effort: 本地交互状态持久化失败仅丢失离线缓存，云端同步仍为真相源 */
  }
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
      'followingSubAccountIds': followingSubAccountIds.toList(growable: false),
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
    if (!ref.mounted) {
      return;
    }
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
      knownSubAccountIds: Set<String>.from(knownSubAccountIds ?? subAccountIds),
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
    this.sharedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.confirmedShareCounts = const <String, int>{},
    this.pendingShareDeltas = const <String, int>{},
    this.confirmedCommentCounts = const <String, int>{},
    this.pendingCommentDeltas = const <String, int>{},
  });

  final Set<String> likedPostIds;
  final Set<String> sharedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> confirmedShareCounts;
  final Map<String, int> pendingShareDeltas;
  final Map<String, int> confirmedCommentCounts;
  final Map<String, int> pendingCommentDeltas;

  bool isLiked(String postId) => likedPostIds.contains(postId);
  bool isShared(String postId) => sharedPostIds.contains(postId);

  bool hasLikeStateFor(String postId) {
    return likedPostIds.contains(postId) || likeCounts.containsKey(postId);
  }

  int likeCountFor(String postId, {int fallback = 0}) {
    return likeCounts[postId] ?? fallback;
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
    Set<String>? sharedPostIds,
    Map<String, int>? likeCounts,
    Map<String, int>? confirmedShareCounts,
    Map<String, int>? pendingShareDeltas,
    Map<String, int>? confirmedCommentCounts,
    Map<String, int>? pendingCommentDeltas,
  }) {
    return PostInteractionState(
      likedPostIds: likedPostIds ?? this.likedPostIds,
      sharedPostIds: sharedPostIds ?? this.sharedPostIds,
      likeCounts: likeCounts ?? this.likeCounts,
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
      sharedPostIds: readSet('sharedPostIds'),
      likeCounts: readIntMap('likeCounts'),
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
      'sharedPostIds': sharedPostIds.toList(growable: false),
      'likeCounts': likeCounts,
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
    if (!ref.mounted) {
      return;
    }
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
    final nextLikeCounts = Map<String, int>.from(state.likeCounts);
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
      final likeCount = snapshot.postLikesCount[postId];
      if (likeCount != null) {
        nextLikeCounts[postId] = likeCount;
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
      likeCounts: nextLikeCounts,
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
