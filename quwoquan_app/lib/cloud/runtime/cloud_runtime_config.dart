/// 云侧运行时配置（端云协同时使用）。
///
/// 约定：本地先跑通单元/集成测试，再切到 remote 对接云侧环境。
class CloudRuntimeConfig {
  const CloudRuntimeConfig._();

  /// Gateway Base URL（例如本机联调网关、或 dev/staging/prod）。
  ///
  /// 通过 `--dart-define=CLOUD_GATEWAY_BASE_URL=...` 注入。
  static const String gatewayBaseUrl = String.fromEnvironment(
    'CLOUD_GATEWAY_BASE_URL',
    defaultValue: 'http://127.0.0.1:18080',
  );
}

