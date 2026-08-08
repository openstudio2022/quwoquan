import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/home_channels_remote_override.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_display_config.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

const Map<String, bool> contentStoryBootstrapFlags = <String, bool>{
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

class ContentCanaryStage {
  const ContentCanaryStage({required this.stage, required this.rolloutPercent});

  final String stage;
  final int rolloutPercent;
}

/// Content Post 对象内的运行配置状态，由 runtime/di 负责装配。
class ContentRuntimeConfigState {
  const ContentRuntimeConfigState({
    required this.featureFlags,
    required this.experimentBucket,
    required this.currentCanaryStage,
    required this.canaryStages,
    required this.clientStateSync,
    required this.comment,
    required this.configHash,
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
  final String? configHash;
  final AppRemoteConfigSource source;
  final List<HomeChannelConfig> homeChannels;
  final IntersectionDisplayConfig intersectionDisplay;

  bool isEnabled(String flag) => featureFlags[flag] ?? false;

  factory ContentRuntimeConfigState.fromAppConfig(
    ContentAppConfig config, {
    required ContentRuntimeConfigState fallback,
    AppRemoteConfigSnapshot? snapshot,
  }) {
    final mergedFlags = <String, bool>{
      ...fallback.featureFlags,
      ..._featureFlagOverrides(config.featureFlags),
    };
    final gray = config.grayRelease;
    final rawStages = gray.canaryMatrix
        .map(
          (window) => ContentCanaryStage(
            stage: window.stage,
            rolloutPercent: window.rolloutPercent,
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
      clientStateSync: _clientStateSyncConfig(
        config.clientStateSync,
        fallback: fallback.clientStateSync,
      ),
      comment: CommentRemoteConfig.fromAppConfig(
        config,
        fallback: fallback.comment,
      ),
      configHash: snapshot?.configHash ?? fallback.configHash,
      source: snapshot?.source ?? fallback.source,
      homeChannels:
          HomeChannelsRemoteOverride.fromAppConfig(config) ??
          fallback.homeChannels,
      intersectionDisplay: IntersectionDisplayConfig.fromAppConfig(config),
    );
  }

  static Map<String, bool> _featureFlagOverrides(
    ContentAppConfigFeatureFlags flags,
  ) {
    return <String, bool>{
      'enable_create_action_entry': ?flags.enableCreateActionEntry,
      'enable_unified_create_editor': ?flags.enableUnifiedCreateEditor,
      'enable_identity_based_surfaces': ?flags.enableIdentityBasedSurfaces,
      'enable_identity_share_template': ?flags.enableIdentityShareTemplate,
      'enable_article_distribution_profiles':
          ?flags.enableArticleDistributionProfiles,
      'enable_article_book_reader': ?flags.enableArticleBookReader,
      'enable_article_page_curl': ?flags.enableArticlePageCurl,
      'enable_shared_video_timeline': ?flags.enableSharedVideoTimeline,
      'enable_video_timeline_preview': ?flags.enableVideoTimelinePreview,
      'enable_hls_cmaf_abr': ?flags.enableHlsCmafAbr,
      'enable_assistant_content_identity_index':
          ?flags.enableAssistantContentIdentityIndex,
      'enable_helper_read': ?flags.enableHelperRead,
      'enable_share_to_circle': ?flags.enableShareToCircle,
      'show_view_count': ?flags.showViewCount,
    };
  }

  static ClientStateSyncConfig _clientStateSyncConfig(
    ContentAppConfigClientStateSync? config, {
    required ClientStateSyncConfig fallback,
  }) {
    if (config == null) return fallback;
    return ClientStateSyncConfig(
      flushDelay: Duration(
        seconds: config.flushDelaySec ?? fallback.flushDelay.inSeconds,
      ),
      retryDelay: Duration(
        seconds: config.retryDelaySec ?? fallback.retryDelay.inSeconds,
      ),
      maxBatchSize: config.maxBatchSize ?? fallback.maxBatchSize,
      maxPendingAge: Duration(
        seconds: config.maxPendingAgeSec ?? fallback.maxPendingAge.inSeconds,
      ),
      flushOnForegroundResume:
          config.flushOnForegroundResume ?? fallback.flushOnForegroundResume,
      flushOnNetworkRecovered:
          config.flushOnNetworkRecovered ?? fallback.flushOnNetworkRecovered,
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
