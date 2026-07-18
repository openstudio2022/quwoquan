/// 云侧运行时配置（端云协同时使用）。
///
/// 约定：alpha 先跑通单实例验证，beta 做本地端云联调，再切到 gamma/prod。
/// 生产灰度属于 `prod` 语义下的 rollout stage，不额外占用环境枚举。
class CloudRuntimeConfig {
  const CloudRuntimeConfig._();

  /// App 运行环境：alpha / beta / gamma / prod。
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
    defaultValue: '',
  );

  /// 头像 CDN Base URL。展示 URL 由服务端返回，App 仅用于环境包审计与 beta 联调报告。
  static const String mediaAvatarCdnBaseUrl = String.fromEnvironment(
    'MEDIA_AVATAR_CDN_BASE_URL',
    defaultValue: '',
  );

  static const String mediaImageCdnBaseUrl = String.fromEnvironment(
    'MEDIA_IMAGE_CDN_BASE_URL',
    defaultValue: '',
  );

  static const String mediaVideoCdnBaseUrl = String.fromEnvironment(
    'MEDIA_VIDEO_CDN_BASE_URL',
    defaultValue: '',
  );

  static const String mediaUploadBaseUrl = String.fromEnvironment(
    'MEDIA_UPLOAD_BASE_URL',
    defaultValue: '',
  );

  /// Web 顶部安装提示：移动/Pad 端直接下载 App 或打开商店落地页。
  ///
  /// 生产环境通过 `--dart-define=WEB_APP_MOBILE_DOWNLOAD_URL=...` 注入；
  /// 默认相对路径由 Web 站点承接，不在端侧硬编码安装包地址。
  static const String webAppMobileDownloadUrl = String.fromEnvironment(
    'WEB_APP_MOBILE_DOWNLOAD_URL',
    defaultValue: '/download/mobile',
  );

  /// Web 顶部安装提示：PC 端安装包/下载中心入口。
  static const String webAppDesktopDownloadUrl = String.fromEnvironment(
    'WEB_APP_DESKTOP_DOWNLOAD_URL',
    defaultValue: '/download/desktop',
  );

  /// Web 顶部安装提示：分享给微信/联系人的安装落地页。
  static const String webAppShareInstallUrl = String.fromEnvironment(
    'WEB_APP_SHARE_INSTALL_URL',
    defaultValue: '/download',
  );

  /// Web 顶部安装提示：iOS / Android 具体入口，PC 宽屏用来提示对应安装包。
  static const String webAppIosDownloadUrl = String.fromEnvironment(
    'WEB_APP_IOS_DOWNLOAD_URL',
    defaultValue: '/download/ios',
  );

  static const String webAppAndroidDownloadUrl = String.fromEnvironment(
    'WEB_APP_ANDROID_DOWNLOAD_URL',
    defaultValue: '/download/android',
  );

  /// CDN 主域名（用于判断 URL 是否属于本应用 CDN，启用图片处理参数）。
  static const String cdnDomain = String.fromEnvironment(
    'CDN_DOMAIN',
    defaultValue: '',
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

  /// 当前 prod rollout 诊断阶段，仅用于演练/观测，不参与环境枚举。
  static const String appRolloutMode = String.fromEnvironment(
    'APP_ROLLOUT_MODE',
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
        appRuntimeEnv == 'prod';
  }

  static bool get isValidRolloutMode {
    return appRolloutMode.isEmpty ||
        appRolloutMode == 'gray-initial' ||
        appRolloutMode == 'carry-on' ||
        appRolloutMode == 'full';
  }

  /// 正式启动必须显式注入同一环境包的网关与四类媒体 authority。
  ///
  /// 缺失时直接终止启动，避免直接执行 `flutter run` 意外连接到 alpha。
  static void validateRequiredEndpoints() {
    final endpoints = <String, String>{
      'CLOUD_GATEWAY_BASE_URL': gatewayBaseUrl,
      'MEDIA_AVATAR_CDN_BASE_URL': mediaAvatarCdnBaseUrl,
      'MEDIA_IMAGE_CDN_BASE_URL': mediaImageCdnBaseUrl,
      'MEDIA_VIDEO_CDN_BASE_URL': mediaVideoCdnBaseUrl,
      'MEDIA_UPLOAD_BASE_URL': mediaUploadBaseUrl,
    };
    final invalid = endpoints.entries
        .where((entry) => !_isValidHttpsBaseUrl(entry.value))
        .map((entry) => entry.key)
        .toList(growable: false);
    if (!isValidAppRuntimeEnv || invalid.isNotEmpty) {
      final missing = <String>[
        if (!isValidAppRuntimeEnv) 'APP_RUNTIME_ENV',
        ...invalid,
      ];
      throw StateError(
        'App runtime endpoints must be injected by the environment launcher: '
        '${missing.join(', ')}',
      );
    }
  }

  static bool _isValidHttpsBaseUrl(String raw) {
    final uri = Uri.tryParse(raw.trim());
    return uri != null &&
        uri.scheme.toLowerCase() == 'https' &&
        uri.host.isNotEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }
}
