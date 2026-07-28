part of 'app_providers.dart';

ContentRuntimeConfigState buildProductionContentRuntimeConfigDefaults() {
  return ContentRuntimeConfigState(
    featureFlags: <String, bool>{...ContentUIConfig.featureFlags},
    experimentBucket: 'control',
    currentCanaryStage: 'control',
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

/// Alpha runner 的显式 content runtime 配置。
///
/// Production Notifier 不读取环境或数据源开关；fixture flags 只能由独立 runner
/// 通过对象级 provider override 注入。
ContentRuntimeConfigState buildAlphaContentRuntimeConfigDefaults() {
  final production = buildProductionContentRuntimeConfigDefaults();
  return ContentRuntimeConfigState(
    featureFlags: <String, bool>{
      ...production.featureFlags,
      ..._contentStoryBootstrapFlags,
    },
    experimentBucket: 'local_story_enabled',
    currentCanaryStage: '100%',
    canaryStages: production.canaryStages,
    clientStateSync: production.clientStateSync,
    comment: production.comment,
    configHash: production.configHash,
    packageVersion: production.packageVersion,
    source: production.source,
    homeChannels: production.homeChannels,
    intersectionDisplay: production.intersectionDisplay,
  );
}
