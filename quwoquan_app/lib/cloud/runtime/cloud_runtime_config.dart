/// compile-time 业务环境配置缺失或非法。
///
/// 该异常只承载脱敏的 define 键集合，不承载 URL、token 或原始异常文本。
final class CloudRuntimeConfigurationException implements Exception {
  CloudRuntimeConfigurationException({
    required this.runtimeEnv,
    required Iterable<String> invalidKeys,
  }) : invalidKeys = List<String>.unmodifiable(invalidKeys);

  final String runtimeEnv;
  final List<String> invalidKeys;

  String get source => 'runtime_define_validation';

  String get message {
    final keys = invalidKeys.isEmpty ? 'unknown' : invalidKeys.join(', ');
    return 'App runtime package is missing or invalid: $keys';
  }

  @override
  String toString() => '$source: $message';
}

/// 云侧运行时配置（端云协同时使用）。
///
/// 环境和业务 endpoint 必须由 Flutter CLI/Xcode build 的同一环境包显式注入。
/// 未注入时不再使用 alpha 作为业务运行时默认值。
class CloudRuntimeConfig {
  const CloudRuntimeConfig._();

  /// App 运行环境：alpha / beta / gamma / prod。
  ///
  /// 通过 `--dart-define=APP_RUNTIME_ENV=...` 注入。
  static const String appRuntimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: '',
  );

  /// Gateway Base URL（例如本机联调网关、或 dev/staging/prod）。
  ///
  /// 通过 `--dart-define=CLOUD_GATEWAY_BASE_URL=...` 注入。
  static const String gatewayBaseUrl = String.fromEnvironment(
    'CLOUD_GATEWAY_BASE_URL',
    defaultValue: '',
  );

  static const String realtimeConnectionUrl = String.fromEnvironment(
    'REALTIME_CONNECTION_URL',
    defaultValue: '',
  );

  static const String publicWebBaseUrl = String.fromEnvironment(
    'PUBLIC_WEB_BASE_URL',
    defaultValue: '',
  );

  static const String appDownloadBaseUrl = String.fromEnvironment(
    'APP_DOWNLOAD_BASE_URL',
    defaultValue: '',
  );

  static const String legalBaseUrl = String.fromEnvironment(
    'APP_LEGAL_BASE_URL',
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

  /// 媒体房间连接地址，仅由受控环境包注入平台媒体 adapter。
  ///
  /// 通过 `--dart-define=RTC_MEDIA_CONNECTION_URL=...` 注入；它绝不能由
  /// CallSession operation 响应透传。
  static const String rtcMediaConnectionUrl = String.fromEnvironment(
    'RTC_MEDIA_CONNECTION_URL',
    defaultValue: '',
  );

  /// Web 顶部安装提示：移动/Pad 端进入官网平台恢复入口。
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

  /// Web 顶部安装提示：iOS PWA / Android APK 具体入口。
  static const String webAppIosDownloadUrl = String.fromEnvironment(
    'WEB_APP_IOS_DOWNLOAD_URL',
    defaultValue: '/download/ios',
  );

  static const String webAppAndroidDownloadUrl = String.fromEnvironment(
    'WEB_APP_ANDROID_DOWNLOAD_URL',
    defaultValue: '/download/android',
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

  /// 启动入口标识，仅用于诊断；热重启不会重新编译该值。
  static const String launchMode = String.fromEnvironment(
    'QWQ_APP_LAUNCH_MODE',
    defaultValue: 'unknown',
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

  /// 返回编译期业务 define 中缺失或非法的键，不包含任何 endpoint 值。
  static List<String> get missingRequiredDefineKeys {
    final invalid = <String>[
      if (!isValidAppRuntimeEnv) 'APP_RUNTIME_ENV',
      if (!_isValidHttpsBaseUrl(gatewayBaseUrl)) 'CLOUD_GATEWAY_BASE_URL',
      if (!_isValidSecureWebSocketUrl(realtimeConnectionUrl))
        'REALTIME_CONNECTION_URL',
      if (!_isValidHttpsBaseUrl(publicWebBaseUrl)) 'PUBLIC_WEB_BASE_URL',
      if (!_isValidHttpsBaseUrl(appDownloadBaseUrl)) 'APP_DOWNLOAD_BASE_URL',
      if (!_isValidHttpsBaseUrl(legalBaseUrl)) 'APP_LEGAL_BASE_URL',
      if (!_isValidHttpsBaseUrl(mediaAvatarCdnBaseUrl))
        'MEDIA_AVATAR_CDN_BASE_URL',
      if (!_isValidHttpsBaseUrl(mediaImageCdnBaseUrl))
        'MEDIA_IMAGE_CDN_BASE_URL',
      if (!_isValidHttpsBaseUrl(mediaVideoCdnBaseUrl))
        'MEDIA_VIDEO_CDN_BASE_URL',
      if (!_isValidHttpsBaseUrl(mediaUploadBaseUrl)) 'MEDIA_UPLOAD_BASE_URL',
      if (!_isValidSecureWebSocketUrl(rtcMediaConnectionUrl))
        'RTC_MEDIA_CONNECTION_URL',
    ];
    return List<String>.unmodifiable(invalid);
  }

  /// 只用于启动证据的环境摘要；绝不返回 URL。
  static Map<String, String> get runtimeDefineSummary {
    return <String, String>{
      'runtimeEnv': appRuntimeEnv.isEmpty ? 'unknown' : appRuntimeEnv,
      'launchMode': launchMode,
      'configurationState': missingRequiredDefineKeys.isEmpty
          ? 'complete'
          : 'invalid',
      'missingKeys': missingRequiredDefineKeys.join(','),
    };
  }

  /// 正式启动必须显式注入同一环境包的网关与四类媒体 authority。
  ///
  /// 缺失时直接终止启动，避免直接执行 `flutter run` 意外连接到 alpha。
  static void validateRequiredEndpoints() {
    validateRuntimePackage(
      runtimeEnv: appRuntimeEnv,
      gatewayBaseUrl: gatewayBaseUrl,
      realtimeConnectionUrl: realtimeConnectionUrl,
      publicWebBaseUrl: publicWebBaseUrl,
      appDownloadBaseUrl: appDownloadBaseUrl,
      legalBaseUrl: legalBaseUrl,
      mediaAvatarCdnBaseUrl: mediaAvatarCdnBaseUrl,
      mediaImageCdnBaseUrl: mediaImageCdnBaseUrl,
      mediaVideoCdnBaseUrl: mediaVideoCdnBaseUrl,
      mediaUploadBaseUrl: mediaUploadBaseUrl,
      rtcMediaConnectionUrl: rtcMediaConnectionUrl,
    );
  }

  /// 验证业务运行环境包；观测/SLS 不属于客户端启动前置条件。
  static void validateRuntimePackage({
    required String runtimeEnv,
    required String gatewayBaseUrl,
    required String realtimeConnectionUrl,
    required String publicWebBaseUrl,
    required String appDownloadBaseUrl,
    required String legalBaseUrl,
    required String mediaAvatarCdnBaseUrl,
    required String mediaImageCdnBaseUrl,
    required String mediaVideoCdnBaseUrl,
    required String mediaUploadBaseUrl,
    required String rtcMediaConnectionUrl,
  }) {
    final endpoints = <String, String>{
      'CLOUD_GATEWAY_BASE_URL': gatewayBaseUrl,
      'PUBLIC_WEB_BASE_URL': publicWebBaseUrl,
      'APP_DOWNLOAD_BASE_URL': appDownloadBaseUrl,
      'APP_LEGAL_BASE_URL': legalBaseUrl,
      'MEDIA_AVATAR_CDN_BASE_URL': mediaAvatarCdnBaseUrl,
      'MEDIA_IMAGE_CDN_BASE_URL': mediaImageCdnBaseUrl,
      'MEDIA_VIDEO_CDN_BASE_URL': mediaVideoCdnBaseUrl,
      'MEDIA_UPLOAD_BASE_URL': mediaUploadBaseUrl,
    };
    // 必须用可变 List 字面量；空 where().toList() 在部分运行时会得到定长列表，
    // 随后 add RTC 键会抛 UnsupportedError，掩盖真正的配置错误。
    final invalidEndpoints = <String>[
      for (final entry in endpoints.entries)
        if (!_isValidHttpsBaseUrl(entry.value)) entry.key,
    ];
    if (!_isValidSecureWebSocketUrl(rtcMediaConnectionUrl)) {
      invalidEndpoints.add('RTC_MEDIA_CONNECTION_URL');
    }
    if (!_isValidSecureWebSocketUrl(realtimeConnectionUrl)) {
      invalidEndpoints.add('REALTIME_CONNECTION_URL');
    }
    final validRuntimeEnv =
        runtimeEnv == 'alpha' ||
        runtimeEnv == 'beta' ||
        runtimeEnv == 'gamma' ||
        runtimeEnv == 'prod';
    if (!validRuntimeEnv || invalidEndpoints.isNotEmpty) {
      final invalid = <String>[
        if (!validRuntimeEnv) 'APP_RUNTIME_ENV',
        ...invalidEndpoints,
      ];
      throw CloudRuntimeConfigurationException(
        runtimeEnv: runtimeEnv,
        invalidKeys: invalid,
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

  static bool _isValidSecureWebSocketUrl(String raw) {
    final uri = Uri.tryParse(raw.trim());
    return uri != null &&
        uri.scheme.toLowerCase() == 'wss' &&
        uri.host.isNotEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }
}
