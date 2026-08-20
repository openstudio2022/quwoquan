import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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
  static bool _nativeRuntimePackageHydrated = false;
  static bool _enforceNativeLaunchBinding = true;

  static ResolvedRuntimePackage get _resolution =>
      RuntimePackageResolver.resolve(
        compiledPackage: _compiledRuntimePackage,
        nativeValues: _nativeRuntimePackage,
        nativeRuntimePackageHydrated: _nativeRuntimePackageHydrated,
        enforceNativeLaunchBinding: _enforceNativeLaunchBinding,
      );

  static String _runtimeValue(String key) {
    // 任一 compile-time runtime define 存在时，整包只能来自 compile-time；
    // 缺失键必须 fail-closed，禁止与 native package 拼成第二份混合配置。
    return _resolution.valueFor(key);
  }

  /// App 运行环境：alpha / beta / gamma / prod。
  ///
  /// 通过 `--dart-define=APP_RUNTIME_ENV=...` 注入。
  static const String _compiledAppRuntimeEnv = String.fromEnvironment(
    'APP_RUNTIME_ENV',
    defaultValue: '',
  );
  static String get appRuntimeEnv => _runtimeValue('APP_RUNTIME_ENV');

  /// Gateway Base URL（例如本机联调网关、或 dev/staging/prod）。
  ///
  /// 通过 `--dart-define=CLOUD_GATEWAY_BASE_URL=...` 注入。
  static const String _compiledGatewayBaseUrl = String.fromEnvironment(
    'CLOUD_GATEWAY_BASE_URL',
    defaultValue: '',
  );
  static String get gatewayBaseUrl => _runtimeValue('CLOUD_GATEWAY_BASE_URL');

  static const String _compiledRealtimeConnectionUrl = String.fromEnvironment(
    'REALTIME_CONNECTION_URL',
    defaultValue: '',
  );
  static String get realtimeConnectionUrl =>
      _runtimeValue('REALTIME_CONNECTION_URL');

  static const String _compiledPublicWebBaseUrl = String.fromEnvironment(
    'PUBLIC_WEB_BASE_URL',
    defaultValue: '',
  );
  static String get publicWebBaseUrl => _runtimeValue('PUBLIC_WEB_BASE_URL');

  static const String _compiledAppDownloadBaseUrl = String.fromEnvironment(
    'APP_DOWNLOAD_BASE_URL',
    defaultValue: '',
  );
  static String get appDownloadBaseUrl =>
      _runtimeValue('APP_DOWNLOAD_BASE_URL');

  static const String _compiledLegalBaseUrl = String.fromEnvironment(
    'APP_LEGAL_BASE_URL',
    defaultValue: '',
  );
  static String get legalBaseUrl => _runtimeValue('APP_LEGAL_BASE_URL');

  /// 头像 CDN Base URL。展示 URL 由服务端返回，App 仅用于环境包审计与 beta 联调报告。
  static const String _compiledMediaAvatarCdnBaseUrl = String.fromEnvironment(
    'MEDIA_AVATAR_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaAvatarCdnBaseUrl =>
      _runtimeValue('MEDIA_AVATAR_CDN_BASE_URL');

  static const String _compiledMediaImageCdnBaseUrl = String.fromEnvironment(
    'MEDIA_IMAGE_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaImageCdnBaseUrl =>
      _runtimeValue('MEDIA_IMAGE_CDN_BASE_URL');

  static const String _compiledMediaVideoCdnBaseUrl = String.fromEnvironment(
    'MEDIA_VIDEO_CDN_BASE_URL',
    defaultValue: '',
  );
  static String get mediaVideoCdnBaseUrl =>
      _runtimeValue('MEDIA_VIDEO_CDN_BASE_URL');

  static const String _compiledMediaUploadBaseUrl = String.fromEnvironment(
    'MEDIA_UPLOAD_BASE_URL',
    defaultValue: '',
  );
  static String get mediaUploadBaseUrl =>
      _runtimeValue('MEDIA_UPLOAD_BASE_URL');

  /// 媒体房间连接地址，仅由受控环境包注入平台媒体 adapter。
  ///
  /// 通过 `--dart-define=RTC_MEDIA_CONNECTION_URL=...` 注入；它绝不能由
  /// CallSession operation 响应透传。
  static const String _compiledRtcMediaConnectionUrl = String.fromEnvironment(
    'RTC_MEDIA_CONNECTION_URL',
    defaultValue: '',
  );
  static String get rtcMediaConnectionUrl =>
      _runtimeValue('RTC_MEDIA_CONNECTION_URL');

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
    final value = _runtimeValue('QWQ_APP_LAUNCH_MODE');
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
    final value = _runtimeValue('APP_LAUNCH_POLICY');
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
    return _resolution.isValidAppRuntimeEnv;
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
    return _resolution.shouldLoadNativeRuntimePackage;
  }

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
  };

  static void hydrateFromNativeRuntimePackage(
    Map<String, String> values, {
    bool enforceNativeLaunchBinding = true,
  }) {
    _nativeRuntimePackage = Map<String, String>.unmodifiable(<String, String>{
      for (final entry in values.entries)
        if ((runtimePackageAllowedKeys.contains(entry.key) ||
                launchIdentityKeys.contains(entry.key) ||
                runtimePackageForbiddenContentKeys.contains(entry.key)) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    });
    _nativeRuntimePackageHydrated = true;
    _enforceNativeLaunchBinding = enforceNativeLaunchBinding;
  }

  static String get launchTarget => _resolution.launchTarget;

  static String get effectiveLaunchManifestDigest =>
      _resolution.effectiveLaunchManifestDigest;

  /// 返回有效 runtime package 中缺失或非法的键，不包含任何 endpoint 值。
  static List<String> get missingRequiredDefineKeys {
    return _resolution.missingRequiredDefineKeys;
  }

  /// 只用于启动证据的环境摘要；绝不返回 URL。
  static Map<String, String> get runtimeDefineSummary {
    return _resolution.runtimeDefineSummary;
  }

  /// runtime package 未水合或非法时的 typed unavailable；配置完整时返回 null。
  ///
  /// 业务请求不得在配置不可用时抛裸异常或拼装半份配置，故此处只返回脱敏的
  /// configurationState 与缺失键集合，绝不返回 URL。
  ///
  /// [summary] 只替换被判读的那份摘要，不碰任何全局状态：门禁把一整包
  /// runtime define 编进测试二进制，全局解析结果恒为 complete，未水合与
  /// 半份包这两种态在进程里根本造不出来，判读规则也就无从被覆盖。留这个
  /// 入参是让规则本身可被独立喂数，compile-time 优先级仍由全局链路决定。
  static RuntimeFailure? runtimeAvailabilityFailure({
    Map<String, String>? summary,
  }) {
    final resolved = summary ?? runtimeDefineSummary;
    final configurationState = resolved['configurationState'] ?? 'invalid';
    if (configurationState == 'complete') {
      return null;
    }
    const errorCode = OpsEventRecordErrorCode.startupConfigurationInvalid;
    return RuntimeFailure(
      code: errorCode.code,
      semanticReason: errorCode.name,
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'runtime.startup',
        functionModule: 'runtime_config',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'configurationState',
            value: configurationState,
          ),
          RuntimeContextAttribute(
            key: 'invalidDefineKeys',
            value: resolved['missingKeys'] ?? '',
          ),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'inline',
      ),
    );
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
    final invalid = RuntimePackageValidator.invalidRuntimeEndpointKeys(
      runtimeEnv: runtimeEnv,
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
    if (invalid.isNotEmpty) {
      throw CloudRuntimeConfigurationException(
        runtimeEnv: runtimeEnv,
        invalidKeys: invalid,
      );
    }
  }
}
