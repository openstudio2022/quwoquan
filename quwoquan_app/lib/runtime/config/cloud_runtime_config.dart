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
/// canonical launcher 通过 Dart defines 注入；裸 Flutter Debug 则读取平台构建阶段
/// 从 metadata 生成并嵌入制品的同一份 native runtime package。
class CloudRuntimeConfig {
  const CloudRuntimeConfig._();

  static Map<String, String> _nativeRuntimePackage = const <String, String>{};
  static Map<String, String> _nativeContentBinding = const <String, String>{};
  static Map<String, String> _nativeLaunchIdentity = const <String, String>{};
  static List<String> _nativeRuntimeDriftKeys = const <String>[];
  static bool _nativeRuntimePackageHydrated = false;
  static bool _enforceNativeLaunchBinding = true;

  static String _runtimeValue(String key, String compiledValue) {
    // 任一 compile-time runtime define 存在时，整包只能来自 compile-time；
    // 缺失键必须 fail-closed，禁止与 native package 拼成第二份混合配置。
    if (!shouldLoadNativeRuntimePackage) {
      return compiledValue;
    }
    return _nativeRuntimePackage[key] ?? '';
  }

  /// App 运行环境：alpha / beta / gamma / prod。
  ///
  /// 通过 `--dart-define=APP_RUNTIME_ENV=...` 注入。
  static const String _compiledAppRuntimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: '',
  );
  static String get appRuntimeEnv =>
      _runtimeValue('APP_RUNTIME_ENV', _compiledAppRuntimeEnv);

  /// Gateway Base URL（例如本机联调网关、或 dev/staging/prod）。
  ///
  /// 通过 `--dart-define=CLOUD_GATEWAY_BASE_URL=...` 注入。
  static const String _compiledGatewayBaseUrl = String.fromEnvironment(
    'CLOUD_GATEWAY_BASE_URL',
    defaultValue: '',
  );
  static String get gatewayBaseUrl =>
      _runtimeValue('CLOUD_GATEWAY_BASE_URL', _compiledGatewayBaseUrl);

  static const String _compiledRealtimeConnectionUrl = String.fromEnvironment(
    'REALTIME_CONNECTION_URL',
    defaultValue: '',
  );
  static String get realtimeConnectionUrl =>
      _runtimeValue('REALTIME_CONNECTION_URL', _compiledRealtimeConnectionUrl);

  static const String _compiledPublicWebBaseUrl = String.fromEnvironment(
    'PUBLIC_WEB_BASE_URL',
    defaultValue: '',
  );
  static String get publicWebBaseUrl =>
      _runtimeValue('PUBLIC_WEB_BASE_URL', _compiledPublicWebBaseUrl);

  static const String _compiledAppDownloadBaseUrl = String.fromEnvironment(
    'APP_DOWNLOAD_BASE_URL',
    defaultValue: '',
  );
  static String get appDownloadBaseUrl =>
      _runtimeValue('APP_DOWNLOAD_BASE_URL', _compiledAppDownloadBaseUrl);

  static const String _compiledLegalBaseUrl = String.fromEnvironment(
    'APP_LEGAL_BASE_URL',
    defaultValue: '',
  );
  static String get legalBaseUrl =>
      _runtimeValue('APP_LEGAL_BASE_URL', _compiledLegalBaseUrl);

  /// 头像 CDN Base URL。展示 URL 由服务端返回，App 仅用于环境包审计与 beta 联调报告。
  static const String _compiledMediaAvatarCdnBaseUrl = String.fromEnvironment(
    'MEDIA_AVATAR_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaAvatarCdnBaseUrl => _runtimeValue(
    'MEDIA_AVATAR_CDN_BASE_URL',
    _compiledMediaAvatarCdnBaseUrl,
  );

  static const String _compiledMediaImageCdnBaseUrl = String.fromEnvironment(
    'MEDIA_IMAGE_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaImageCdnBaseUrl =>
      _runtimeValue('MEDIA_IMAGE_CDN_BASE_URL', _compiledMediaImageCdnBaseUrl);

  static const String _compiledMediaVideoCdnBaseUrl = String.fromEnvironment(
    'MEDIA_VIDEO_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaVideoCdnBaseUrl =>
      _runtimeValue('MEDIA_VIDEO_CDN_BASE_URL', _compiledMediaVideoCdnBaseUrl);

  static const String _compiledMediaUploadBaseUrl = String.fromEnvironment(
    'MEDIA_UPLOAD_BASE_URL',
    defaultValue: '',
  );
  static String get mediaUploadBaseUrl =>
      _runtimeValue('MEDIA_UPLOAD_BASE_URL', _compiledMediaUploadBaseUrl);

  /// 媒体房间连接地址，仅由受控环境包注入平台媒体 adapter。
  ///
  /// 通过 `--dart-define=RTC_MEDIA_CONNECTION_URL=...` 注入；它绝不能由
  /// CallSession operation 响应透传。
  static const String _compiledRtcMediaConnectionUrl = String.fromEnvironment(
    'RTC_MEDIA_CONNECTION_URL',
    defaultValue: '',
  );
  static String get rtcMediaConnectionUrl =>
      _runtimeValue('RTC_MEDIA_CONNECTION_URL', _compiledRtcMediaConnectionUrl);

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
  static const String _compiledLaunchMode = String.fromEnvironment(
    'QWQ_APP_LAUNCH_MODE',
    defaultValue: '',
  );
  static String get launchMode {
    final value = _runtimeValue('QWQ_APP_LAUNCH_MODE', _compiledLaunchMode);
    return value.isEmpty ? 'unknown' : value;
  }

  /// 测试环境使用 test_live，正式发布唯一使用 prod_release。
  static const String testLiveLaunchPolicy = 'test_live';
  static const String prodReleaseLaunchPolicy = 'prod_release';

  static const String _compiledLaunchPolicy = String.fromEnvironment(
    'APP_LAUNCH_POLICY',
    defaultValue: '',
  );
  static String get launchPolicy {
    final value = _runtimeValue('APP_LAUNCH_POLICY', _compiledLaunchPolicy);
    return value.isEmpty ? 'unknown' : value;
  }

  static const String _compiledContentBindingState = String.fromEnvironment(
    'CONTENT_BINDING_STATE',
    defaultValue: '',
  );
  static String get declaredContentBindingState {
    final value = _runtimeValue(
      'CONTENT_BINDING_STATE',
      _compiledContentBindingState,
    );
    return value.isEmpty ? 'unknown' : value;
  }

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

  /// 只有 runtime 相关 compile-time define 全部为空时才读取 native package。
  /// 部分显式配置必须继续 fail-closed，不能与自动 Alpha handoff 拼接。
  static bool get shouldLoadNativeRuntimePackage {
    return <String>[
      _compiledAppRuntimeEnv,
      _compiledGatewayBaseUrl,
      _compiledRealtimeConnectionUrl,
      _compiledPublicWebBaseUrl,
      _compiledAppDownloadBaseUrl,
      _compiledLegalBaseUrl,
      _compiledMediaAvatarCdnBaseUrl,
      _compiledMediaImageCdnBaseUrl,
      _compiledMediaVideoCdnBaseUrl,
      _compiledMediaUploadBaseUrl,
      _compiledRtcMediaConnectionUrl,
      _compiledLaunchPolicy,
      _compiledContentBindingState,
    ].every((value) => value.isEmpty);
  }

  static const Set<String> _nativeRuntimeAllowedKeys = <String>{
    'APP_RUNTIME_ENV',
    'CLOUD_GATEWAY_BASE_URL',
    'APP_LEGAL_BASE_URL',
    'PUBLIC_WEB_BASE_URL',
    'APP_DOWNLOAD_BASE_URL',
    'REALTIME_CONNECTION_URL',
    'MEDIA_AVATAR_CDN_BASE_URL',
    'MEDIA_IMAGE_CDN_BASE_URL',
    'MEDIA_VIDEO_CDN_BASE_URL',
    'MEDIA_UPLOAD_BASE_URL',
    'RTC_MEDIA_CONNECTION_URL',
    'QWQ_APP_LAUNCH_MODE',
    'APP_LAUNCH_POLICY',
    'CONTENT_BINDING_STATE',
  };

  static Map<String, String> get _compiledRuntimePackage => <String, String>{
    'APP_RUNTIME_ENV': _compiledAppRuntimeEnv,
    'CLOUD_GATEWAY_BASE_URL': _compiledGatewayBaseUrl,
    'APP_LEGAL_BASE_URL': _compiledLegalBaseUrl,
    'PUBLIC_WEB_BASE_URL': _compiledPublicWebBaseUrl,
    'APP_DOWNLOAD_BASE_URL': _compiledAppDownloadBaseUrl,
    'REALTIME_CONNECTION_URL': _compiledRealtimeConnectionUrl,
    'MEDIA_AVATAR_CDN_BASE_URL': _compiledMediaAvatarCdnBaseUrl,
    'MEDIA_IMAGE_CDN_BASE_URL': _compiledMediaImageCdnBaseUrl,
    'MEDIA_VIDEO_CDN_BASE_URL': _compiledMediaVideoCdnBaseUrl,
    'MEDIA_UPLOAD_BASE_URL': _compiledMediaUploadBaseUrl,
    'RTC_MEDIA_CONNECTION_URL': _compiledRtcMediaConnectionUrl,
    'QWQ_APP_LAUNCH_MODE': _compiledLaunchMode,
    'APP_LAUNCH_POLICY': _compiledLaunchPolicy,
    'CONTENT_BINDING_STATE': _compiledContentBindingState,
  };

  static void hydrateFromNativeRuntimePackage(
    Map<String, String> values, {
    bool enforceNativeLaunchBinding = true,
  }) {
    const contentBindingKeys = <String>{
      'contentReleaseId',
      'contentManifestDigest',
      'contentReadinessReceiptDigest',
    };
    const launchIdentityKeys = <String>{
      'launchTarget',
      'effectiveLaunchManifestDigest',
    };
    _nativeLaunchIdentity = Map<String, String>.unmodifiable(<String, String>{
      for (final entry in values.entries)
        if (launchIdentityKeys.contains(entry.key) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    });
    _nativeContentBinding = Map<String, String>.unmodifiable(<String, String>{
      for (final entry in values.entries)
        if (contentBindingKeys.contains(entry.key) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    });
    _nativeRuntimePackage = Map<String, String>.unmodifiable(<String, String>{
      for (final entry in values.entries)
        if (_nativeRuntimeAllowedKeys.contains(entry.key) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    });
    _nativeRuntimePackageHydrated = true;
    _enforceNativeLaunchBinding = enforceNativeLaunchBinding;
    _nativeRuntimeDriftKeys =
        shouldLoadNativeRuntimePackage || !enforceNativeLaunchBinding
        ? const <String>[]
        : List<String>.unmodifiable(
            _nativeRuntimeAllowedKeys.where(
              (key) =>
                  _nativeRuntimePackage[key] != _compiledRuntimePackage[key],
            ),
          );
  }

  static void clearNativeRuntimePackageForTest() {
    _nativeRuntimePackage = const <String, String>{};
    _nativeContentBinding = const <String, String>{};
    _nativeLaunchIdentity = const <String, String>{};
    _nativeRuntimeDriftKeys = const <String>[];
    _nativeRuntimePackageHydrated = false;
    _enforceNativeLaunchBinding = true;
  }

  static String get contentReleaseId =>
      _nativeContentBinding['contentReleaseId'] ?? '';

  static String get contentManifestDigest =>
      _nativeContentBinding['contentManifestDigest'] ?? '';

  static String get contentReadinessReceiptDigest =>
      _nativeContentBinding['contentReadinessReceiptDigest'] ?? '';

  static String get launchTarget => _nativeLaunchIdentity['launchTarget'] ?? '';

  static String get effectiveLaunchManifestDigest =>
      _nativeLaunchIdentity['effectiveLaunchManifestDigest'] ?? '';

  static bool get hasCompleteContentBinding {
    final digestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
    return contentReleaseId.isNotEmpty &&
        digestPattern.hasMatch(contentManifestDigest) &&
        digestPattern.hasMatch(contentReadinessReceiptDigest);
  }

  static bool get _hasAnyContentBinding =>
      contentReleaseId.isNotEmpty ||
      contentManifestDigest.isNotEmpty ||
      contentReadinessReceiptDigest.isNotEmpty;

  static bool get requiresReleaseBoundContent =>
      declaredContentBindingState == 'bound' ||
      (_enforceNativeLaunchBinding && launchPolicy == prodReleaseLaunchPolicy);

  /// 裸 `flutter run` 没有显式内容绑定时不能静默请求 Remote。
  ///
  /// canonical launcher 的 `ui-only` 仍可进入安全 Shell，并由服务端
  /// `no_active_release` 表达无内容；direct Debug 则先进入 metadata 驱动的
  /// 开发配置恢复，避免把启动方式错误伪装成普通服务不可用。
  static bool get blocksRemoteForDirectUnboundLaunch =>
      _enforceNativeLaunchBinding &&
      launchMode == 'direct_flutter_run' &&
      launchPolicy == testLiveLaunchPolicy &&
      declaredContentBindingState == 'unbound' &&
      !_hasAnyContentBinding;

  /// 返回有效 runtime package 中缺失或非法的键，不包含任何 endpoint 值。
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
      if (launchPolicy != testLiveLaunchPolicy &&
          launchPolicy != prodReleaseLaunchPolicy)
        'APP_LAUNCH_POLICY',
      if (launchPolicy == testLiveLaunchPolicy && appRuntimeEnv == 'prod')
        'APP_LAUNCH_POLICY',
      if (launchPolicy == prodReleaseLaunchPolicy && appRuntimeEnv != 'prod')
        'APP_LAUNCH_POLICY',
      if (launchPolicy == testLiveLaunchPolicy &&
          declaredContentBindingState != 'unbound' &&
          declaredContentBindingState != 'bound')
        'CONTENT_BINDING_STATE',
      if (launchPolicy == prodReleaseLaunchPolicy &&
          declaredContentBindingState != 'bound')
        'CONTENT_BINDING_STATE',
      if (declaredContentBindingState == 'unbound' && _hasAnyContentBinding)
        'CONTENT_BINDING_STATE',
      if (blocksRemoteForDirectUnboundLaunch) 'CONTENT_BINDING_STATE',
      if (requiresReleaseBoundContent && contentReleaseId.isEmpty)
        'contentReleaseId',
      if (requiresReleaseBoundContent && launchTarget != '$appRuntimeEnv-local')
        'launchTarget',
      if (requiresReleaseBoundContent &&
          !RegExp(
            r'^sha256:[0-9a-f]{64}$',
          ).hasMatch(effectiveLaunchManifestDigest))
        'effectiveLaunchManifestDigest',
      if (requiresReleaseBoundContent &&
          !RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(contentManifestDigest))
        'contentManifestDigest',
      if (requiresReleaseBoundContent &&
          !RegExp(
            r'^sha256:[0-9a-f]{64}$',
          ).hasMatch(contentReadinessReceiptDigest))
        'contentReadinessReceiptDigest',
      for (final key in _nativeRuntimeDriftKeys) 'NATIVE_RUNTIME_PACKAGE.$key',
    ];
    return List<String>.unmodifiable(invalid);
  }

  /// 只用于启动证据的环境摘要；绝不返回 URL。
  static Map<String, String> get runtimeDefineSummary {
    if (shouldLoadNativeRuntimePackage && !_nativeRuntimePackageHydrated) {
      return const <String, String>{
        'runtimeEnv': 'unknown',
        'launchMode': 'unknown',
        'configurationState': 'pending_native',
        'missingKeys': '',
      };
    }
    return <String, String>{
      'runtimeEnv': appRuntimeEnv.isEmpty ? 'unknown' : appRuntimeEnv,
      'launchMode': launchMode,
      'launchPolicy': launchPolicy,
      'configurationState': missingRequiredDefineKeys.isEmpty
          ? 'complete'
          : 'invalid',
      'contentBindingState':
          declaredContentBindingState == 'unbound' && !_hasAnyContentBinding
          ? 'unbound'
          : declaredContentBindingState == 'bound' && hasCompleteContentBinding
          ? 'bound'
          : 'invalid',
      if (contentReleaseId.isNotEmpty) 'contentReleaseId': contentReleaseId,
      if (contentManifestDigest.isNotEmpty)
        'contentManifestDigest': contentManifestDigest,
      if (contentReadinessReceiptDigest.isNotEmpty)
        'contentReadinessReceiptDigest': contentReadinessReceiptDigest,
      if (launchTarget.isNotEmpty) 'launchTarget': launchTarget,
      if (effectiveLaunchManifestDigest.isNotEmpty)
        'effectiveLaunchManifestDigest': effectiveLaunchManifestDigest,
      'missingKeys': missingRequiredDefineKeys.join(','),
    };
  }

  /// 正式启动必须获得同一环境包的网关与四类媒体 authority。
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
    final invalidPackageKeys = missingRequiredDefineKeys;
    if (invalidPackageKeys.isNotEmpty) {
      throw CloudRuntimeConfigurationException(
        runtimeEnv: appRuntimeEnv,
        invalidKeys: invalidPackageKeys,
      );
    }
  }

  /// 验证业务运行环境包；观测后端不属于客户端启动前置条件。
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
    if (invalidEndpoints.isEmpty) {
      final publicWeb = Uri.parse(publicWebBaseUrl);
      final legal = Uri.parse(legalBaseUrl);
      final appDownload = Uri.parse(appDownloadBaseUrl);
      final mediaAvatar = Uri.parse(mediaAvatarCdnBaseUrl);
      final mediaImage = Uri.parse(mediaImageCdnBaseUrl);
      final mediaVideo = Uri.parse(mediaVideoCdnBaseUrl);
      final mediaUpload = Uri.parse(mediaUploadBaseUrl);
      if (!_sameOrigin(publicWeb, legal) ||
          legal.path != _joinBasePath(publicWeb.path, 'legal')) {
        invalidEndpoints.add('APP_LEGAL_BASE_URL');
      }
      if (!_sameOrigin(mediaAvatar, mediaImage) ||
          !_sameOrigin(mediaImage, mediaVideo) ||
          mediaAvatar.path != '/media/avatar' ||
          mediaImage.path != '/media/image' ||
          mediaVideo.path != '/media/video') {
        invalidEndpoints.addAll(<String>[
          'MEDIA_AVATAR_CDN_BASE_URL',
          'MEDIA_IMAGE_CDN_BASE_URL',
          'MEDIA_VIDEO_CDN_BASE_URL',
        ]);
      }
      if (!_sameOrigin(appDownload, mediaImage) ||
          appDownload.path != '/download') {
        invalidEndpoints.add('APP_DOWNLOAD_BASE_URL');
      }
      if (_sameOrigin(mediaUpload, mediaImage) || mediaUpload.path.isNotEmpty) {
        invalidEndpoints.add('MEDIA_UPLOAD_BASE_URL');
      }
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
        uri.userInfo.isEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }

  static bool _isValidSecureWebSocketUrl(String raw) {
    final uri = Uri.tryParse(raw.trim());
    return uri != null &&
        uri.scheme.toLowerCase() == 'wss' &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }

  static bool _sameOrigin(Uri left, Uri right) =>
      left.scheme.toLowerCase() == right.scheme.toLowerCase() &&
      left.host.toLowerCase() == right.host.toLowerCase() &&
      left.port == right.port;

  static String _joinBasePath(String basePath, String child) {
    final normalized = basePath.replaceFirst(RegExp(r'/+$'), '');
    return '$normalized/$child';
  }
}
