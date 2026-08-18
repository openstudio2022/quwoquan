/// 生产 runtime package 解析与校验（runtime-client-foundation DEC-004）。
///
/// 本文件是 App 启动与 local_contract 测试共用的唯一实现：测试直接构造输入
/// 调用 [RuntimePackageResolver.resolve] 与 [RuntimePackageValidator]，
/// 不经任何 `ForTest` 后门，也不复制第二份校验规则。
///
/// 六维正交约束：environment / platform / BuildMode / launch provenance /
/// install channel / content activation identity 相互独立；本文件只解析
/// 前者中的 runtime package 与 launch identity，内容激活身份由 Content API
/// 响应在运行时下发，绝不出现在 runtime package 中。
library;

/// canonical target → environment 映射。
///
/// 真相源是 `quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml`
/// 的 `target_environment`；local_contract 测试断言本常量与 metadata 一致，
/// 防止 Dart 侧漂移出第二份拓扑。
const Map<String, String> launchTargetEnvironment = <String, String>{
  'alpha-local': 'alpha',
  'beta-local': 'beta',
  'gamma-local': 'gamma',
  'prod-sim': 'prod',
  'prod-hosted': 'prod',
};

/// runtime package 中允许出现的键集合。
const Set<String> runtimePackageAllowedKeys = <String>{
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
};

/// launch identity 观测键（不参与业务分支）。
const Set<String> launchIdentityKeys = <String>{
  'launchTarget',
  'effectiveLaunchManifestDigest',
};

/// 解析后的不可变 runtime package。
final class ResolvedRuntimePackage {
  ResolvedRuntimePackage({
    required Map<String, String> values,
    required Map<String, String> launchIdentity,
    required Iterable<String> driftKeys,
    required this.enforceNativeLaunchBinding,
  }) : values = Map<String, String>.unmodifiable(values),
       launchIdentity = Map<String, String>.unmodifiable(launchIdentity),
       driftKeys = List<String>.unmodifiable(driftKeys);

  final Map<String, String> values;
  final Map<String, String> launchIdentity;
  final List<String> driftKeys;
  final bool enforceNativeLaunchBinding;
}

/// 从原生嵌入的 runtime package 解析不可变配置。
final class RuntimePackageResolver {
  const RuntimePackageResolver._();

  /// 生产解析入口：过滤未声明键、裁剪空白，并在需要时计算与
  /// compile-time package 的漂移键。
  static ResolvedRuntimePackage resolve({
    required Map<String, String> nativeValues,
    required Map<String, String> compiledPackage,
    required bool compiledPackageIsEmpty,
    bool enforceNativeLaunchBinding = true,
  }) {
    final launchIdentity = <String, String>{
      for (final entry in nativeValues.entries)
        if (launchIdentityKeys.contains(entry.key) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    };
    final values = <String, String>{
      for (final entry in nativeValues.entries)
        if (runtimePackageAllowedKeys.contains(entry.key) &&
            entry.value.trim().isNotEmpty)
          entry.key: entry.value.trim(),
    };
    final driftKeys = compiledPackageIsEmpty || !enforceNativeLaunchBinding
        ? const <String>[]
        : runtimePackageAllowedKeys
              .where((key) => values[key] != compiledPackage[key])
              .toList();
    return ResolvedRuntimePackage(
      values: values,
      launchIdentity: launchIdentity,
      driftKeys: driftKeys,
      enforceNativeLaunchBinding: enforceNativeLaunchBinding,
    );
  }
}

/// runtime package 的唯一校验实现。
final class RuntimePackageValidator {
  const RuntimePackageValidator._();

  static const String testLiveLaunchPolicy = 'test_live';
  static const String prodReleaseLaunchPolicy = 'prod_release';

  static final RegExp _sha256Identity = RegExp(r'^sha256:[0-9a-f]{64}$');

  /// 返回 runtime package 中缺失或非法的键；不包含任何 endpoint 值。
  ///
  /// launch provenance（launchMode）不参与任何判定；BuildMode、安装渠道与
  /// 内容身份不属于本校验的输入。
  static List<String> invalidRuntimePackageKeys({
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
    required String launchPolicy,
    required String launchTarget,
    required String effectiveLaunchManifestDigest,
    required bool enforceNativeLaunchBinding,
    List<String> nativeDriftKeys = const <String>[],
  }) {
    final validRuntimeEnv =
        runtimeEnv == 'alpha' ||
        runtimeEnv == 'beta' ||
        runtimeEnv == 'gamma' ||
        runtimeEnv == 'prod';
    final invalid = <String>[
      if (!validRuntimeEnv) 'APP_RUNTIME_ENV',
      if (!isValidHttpsBaseUrl(gatewayBaseUrl)) 'CLOUD_GATEWAY_BASE_URL',
      if (!isValidSecureWebSocketUrl(realtimeConnectionUrl))
        'REALTIME_CONNECTION_URL',
      if (!isValidHttpsBaseUrl(publicWebBaseUrl)) 'PUBLIC_WEB_BASE_URL',
      if (!isValidHttpsBaseUrl(appDownloadBaseUrl)) 'APP_DOWNLOAD_BASE_URL',
      if (!isValidHttpsBaseUrl(legalBaseUrl)) 'APP_LEGAL_BASE_URL',
      if (!isValidHttpsBaseUrl(mediaAvatarCdnBaseUrl))
        'MEDIA_AVATAR_CDN_BASE_URL',
      if (!isValidHttpsBaseUrl(mediaImageCdnBaseUrl))
        'MEDIA_IMAGE_CDN_BASE_URL',
      if (!isValidHttpsBaseUrl(mediaVideoCdnBaseUrl))
        'MEDIA_VIDEO_CDN_BASE_URL',
      if (!isValidHttpsBaseUrl(mediaUploadBaseUrl)) 'MEDIA_UPLOAD_BASE_URL',
      if (!isValidSecureWebSocketUrl(rtcMediaConnectionUrl))
        'RTC_MEDIA_CONNECTION_URL',
      if (launchPolicy != testLiveLaunchPolicy &&
          launchPolicy != prodReleaseLaunchPolicy)
        'APP_LAUNCH_POLICY',
      if (launchPolicy == testLiveLaunchPolicy && runtimeEnv == 'prod')
        'APP_LAUNCH_POLICY',
      if (launchPolicy == prodReleaseLaunchPolicy && runtimeEnv != 'prod')
        'APP_LAUNCH_POLICY',
      // launch identity 一致性：launchTarget 一旦存在，必须映射到当前环境；
      // 映射消费 canonical metadata 的 target_environment，禁止拼接
      // 不存在的 `<env>-local` 之类字面量。
      if (launchTarget.isNotEmpty &&
          launchTargetEnvironment[launchTarget] != runtimeEnv)
        'launchTarget',
      // Release 制品必须内嵌完整 launch identity；direct Debug 与测试可缺席。
      if (enforceNativeLaunchBinding &&
          launchPolicy == prodReleaseLaunchPolicy &&
          launchTarget.isEmpty)
        'launchTarget',
      if (enforceNativeLaunchBinding &&
          launchPolicy == prodReleaseLaunchPolicy &&
          !_sha256Identity.hasMatch(effectiveLaunchManifestDigest))
        'effectiveLaunchManifestDigest',
      if (effectiveLaunchManifestDigest.isNotEmpty &&
          !_sha256Identity.hasMatch(effectiveLaunchManifestDigest))
        'effectiveLaunchManifestDigest',
      for (final key in nativeDriftKeys) 'NATIVE_RUNTIME_PACKAGE.$key',
    ];
    return List<String>.unmodifiable(<String>{...invalid});
  }

  static bool isValidHttpsBaseUrl(String raw) {
    final uri = Uri.tryParse(raw.trim());
    return uri != null &&
        uri.scheme.toLowerCase() == 'https' &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }

  static bool isValidSecureWebSocketUrl(String raw) {
    final uri = Uri.tryParse(raw.trim());
    return uri != null &&
        uri.scheme.toLowerCase() == 'wss' &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment;
  }
}
