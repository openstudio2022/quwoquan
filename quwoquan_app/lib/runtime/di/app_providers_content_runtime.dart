import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_display_config.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_runtime_config_state.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_store.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_app_remote_config_store.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart';

export 'package:quwoquan_app/service/content_service/content/post/application/content_runtime_config_state.dart';

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
    final snapshot = await ref
        .read(appRemoteConfigStoreProvider)
        .readActiveSnapshot();
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
      unawaited(
        ref.read(appRemoteConfigStoreProvider).writeActiveSnapshot(snapshot),
      );
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
    return ContentRuntimeConfigState.fromAppConfig(
      snapshot.content,
      fallback: fallback,
      snapshot: snapshot,
    );
  }

  bool _shouldActivateImmediately(AppRemoteConfigSnapshot snapshot) {
    return snapshot.defaultActivation == 'immediate';
  }
}

final appRemoteConfigStoreProvider = Provider<AppRemoteConfigStore>((ref) {
  return const HiveAppRemoteConfigStore();
});

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
