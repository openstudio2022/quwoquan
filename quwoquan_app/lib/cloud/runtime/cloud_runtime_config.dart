/// 云侧运行时配置（端云协同时使用）。
///
/// 约定：alpha 先跑通单实例验证，beta 做本地端云联调，再切到 gamma/prod-gray/prod。
class CloudRuntimeConfig {
  const CloudRuntimeConfig._();

  /// App 运行环境：alpha / beta / gamma / prod-gray / prod。
  ///
  /// 通过 `--dart-define=APP_RUNTIME_ENV=...` 注入。
  static const String appRuntimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: 'alpha',
  );

  /// Gateway Base URL（例如本机联调网关、或 dev/staging/prod）。
  ///
  /// 通过 `--dart-define=CLOUD_GATEWAY_BASE_URL=...` 注入。
  static const String gatewayBaseUrl = String.fromEnvironment(
    'CLOUD_GATEWAY_BASE_URL',
    defaultValue: 'http://127.0.0.1:18080',
  );

  /// 头像 CDN Base URL。展示 URL 由服务端返回，App 仅用于环境包审计与 beta 联调报告。
  static const String mediaAvatarCdnBaseUrl = String.fromEnvironment(
    'MEDIA_AVATAR_CDN_BASE_URL',
    defaultValue: 'http://127.0.0.1:18088',
  );

  static const String mediaImageCdnBaseUrl = String.fromEnvironment(
    'MEDIA_IMAGE_CDN_BASE_URL',
    defaultValue: 'http://127.0.0.1:18088',
  );

  static const String mediaVideoCdnBaseUrl = String.fromEnvironment(
    'MEDIA_VIDEO_CDN_BASE_URL',
    defaultValue: 'http://127.0.0.1:18088',
  );

  static const String mediaUploadBaseUrl = String.fromEnvironment(
    'MEDIA_UPLOAD_BASE_URL',
    defaultValue: 'http://127.0.0.1:18088',
  );

  /// 当前 App 实例 ID。
  ///
  /// 由多实例启动脚本通过 `--dart-define=APP_INSTANCE_ID=...` 注入，用于
  /// 诊断与报告，不改变业务环境语义。
  static const String appInstanceId = String.fromEnvironment(
    'APP_INSTANCE_ID',
    defaultValue: '',
  );

  /// 当前 App 实例命名空间。
  ///
  /// 由启动脚本注入，便于区分 standalone / beta-manual / gamma-runner 等来源。
  static const String appInstanceNamespace = String.fromEnvironment(
    'APP_INSTANCE_NAMESPACE',
    defaultValue: '',
  );

  /// 地图供应商（baidu / amap）。
  ///
  /// 通过 `--dart-define=MAP_PROVIDER=baidu|amap` 注入。
  static const String mapProvider = String.fromEnvironment(
    'MAP_PROVIDER',
    defaultValue: 'baidu',
  );

  static bool get isValidAppRuntimeEnv {
    return appRuntimeEnv == 'alpha' ||
        appRuntimeEnv == 'beta' ||
        appRuntimeEnv == 'gamma' ||
        appRuntimeEnv == 'prod-gray' ||
        appRuntimeEnv == 'prod';
  }
}
