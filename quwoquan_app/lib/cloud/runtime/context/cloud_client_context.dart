/// Cloud Runtime 只消费该快照，不读取 Flutter、平台 API 或业务 Provider。
final class CloudClientContextSnapshot {
  const CloudClientContextSnapshot({
    required this.sessionId,
    required this.platform,
    required this.appVersion,
    required this.locale,
    this.deviceActorId,
  });

  final String sessionId;
  final String platform;
  final String appVersion;
  final String locale;
  final String? deviceActorId;
}

abstract interface class CloudClientContextProvider {
  CloudClientContextSnapshot snapshot();
}

final class FallbackCloudClientContextProvider
    implements CloudClientContextProvider {
  const FallbackCloudClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'unconfigured',
      platform: 'unknown',
      appVersion: 'dev',
      locale: 'und',
    );
  }
}

/// 存量静态 header builder 的迁移桥；正式 executor 直接注入 provider。
final class CloudClientContextRegistry {
  CloudClientContextRegistry._();

  static CloudClientContextProvider _provider =
      const FallbackCloudClientContextProvider();

  static CloudClientContextProvider get provider => _provider;

  static void configure(CloudClientContextProvider provider) {
    _provider = provider;
  }
}
