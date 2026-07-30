part of 'app_providers.dart';

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

  /// 首页频道（运营资产）：端默认 [ContentUIConfig.homeChannels]，远程整体覆盖、失败回退默认。
  final List<HomeChannelConfig> homeChannels;

  /// 交集展示控制（就地展开行数 / 推荐候选窗），来自 /config/app，失败回退默认。
  final IntersectionDisplayConfig intersectionDisplay;

  bool isEnabled(String flag) => featureFlags[flag] ?? false;

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
    final defaults = buildProductionContentRuntimeConfigDefaults();
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
    final fallback = buildProductionContentRuntimeConfigDefaults();
    state = state.copyWith(isRefreshing: true, errorMessage: () => null);
    try {
      final remoteConfig = await ref
          .read(contentConfigRepositoryProvider)
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

/// 首页频道（运营资产）：端默认 [ContentUIConfig.homeChannels] + `/config/app` 远程覆盖，
/// 失败/缺失回退默认；已按 order 升序。UI 通过本 provider 取频道，禁止硬编码频道列表。
/// 交集展示控制（应用骨架级系统配置），来自 /config/app；UI 通过本 provider 取
/// 就地展开行数等，禁止硬编码或塞进交集列表接口。
final intersectionDisplayConfigProvider = Provider<IntersectionDisplayConfig>((
  ref,
) {
  return ref.watch(contentRuntimeConfigProvider).intersectionDisplay;
});

final homeChannelsProvider = Provider<List<HomeChannelConfig>>((ref) {
  return ref.watch(contentRuntimeConfigProvider).homeChannels;
});

const String _personaManagementFeatureFlag = 'ops.user.persona_management';
const String _personaProfileSyncFeatureFlag = 'ops.user.persona_profile_sync';

bool _runtimeFlagOrEnabledDefault(Ref ref, String flag) {
  final config = ref.watch(contentRuntimeConfigProvider);
  if (config.featureFlags.containsKey(flag)) {
    return config.isEnabled(flag);
  }
  return true;
}

final personaManagementFeatureFlagProvider = Provider<bool>((ref) {
  return _runtimeFlagOrEnabledDefault(ref, _personaManagementFeatureFlag);
});

final personaProfileSyncFeatureFlagProvider = Provider<bool>((ref) {
  return ref.watch(personaManagementFeatureFlagProvider) &&
      _runtimeFlagOrEnabledDefault(ref, _personaProfileSyncFeatureFlag);
});
