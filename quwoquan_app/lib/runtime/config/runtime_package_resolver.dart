/// 生产 runtime package 解析与校验（runtime-client-foundation DEC-004）。
///
/// 本文件是 App 启动与 local_contract 共用的唯一实现。内容激活身份只由
/// Content API 在运行时下发，禁止进入 runtime package、native manifest 或
/// Dart defines。
library;

const Map<String, String> launchTargetEnvironment = <String, String>{
  'alpha-local': 'alpha',
  'beta-local': 'beta',
  'gamma-local': 'gamma',
  'prod-sim': 'prod',
  'prod-hosted': 'prod',
};

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

const Set<String> runtimePackageForbiddenContentKeys = <String>{
  'CONTENT_BINDING_STATE',
  'contentReleaseId',
  'contentManifestDigest',
  'contentReadinessReceiptDigest',
};

const Set<String> launchIdentityKeys = <String>{
  'launchTarget',
  'effectiveLaunchManifestDigest',
};

enum RuntimePackageSource { compileTime, native }

final class ResolvedRuntimePackage {
  ResolvedRuntimePackage({
    required this.source,
    required Map<String, String> values,
    required Map<String, String> launchIdentity,
    required Iterable<String> driftKeys,
    required Iterable<String> forbiddenInputKeys,
    required this.nativeRuntimePackageHydrated,
    required this.enforceNativeLaunchBinding,
  }) : values = Map<String, String>.unmodifiable(values),
       launchIdentity = Map<String, String>.unmodifiable(launchIdentity),
       driftKeys = List<String>.unmodifiable(driftKeys),
       forbiddenInputKeys = List<String>.unmodifiable(forbiddenInputKeys);

  final RuntimePackageSource source;
  final Map<String, String> values;
  final Map<String, String> launchIdentity;
  final List<String> driftKeys;
  final List<String> forbiddenInputKeys;
  final bool nativeRuntimePackageHydrated;
  final bool enforceNativeLaunchBinding;

  bool get shouldLoadNativeRuntimePackage =>
      source == RuntimePackageSource.native;

  String valueFor(String key) => values[key] ?? '';

  String get appRuntimeEnv => valueFor('APP_RUNTIME_ENV');
  String get gatewayBaseUrl => valueFor('CLOUD_GATEWAY_BASE_URL');
  String get realtimeConnectionUrl => valueFor('REALTIME_CONNECTION_URL');
  String get publicWebBaseUrl => valueFor('PUBLIC_WEB_BASE_URL');
  String get appDownloadBaseUrl => valueFor('APP_DOWNLOAD_BASE_URL');
  String get legalBaseUrl => valueFor('APP_LEGAL_BASE_URL');
  String get mediaAvatarCdnBaseUrl => valueFor('MEDIA_AVATAR_CDN_BASE_URL');
  String get mediaImageCdnBaseUrl => valueFor('MEDIA_IMAGE_CDN_BASE_URL');
  String get mediaVideoCdnBaseUrl => valueFor('MEDIA_VIDEO_CDN_BASE_URL');
  String get mediaUploadBaseUrl => valueFor('MEDIA_UPLOAD_BASE_URL');
  String get rtcMediaConnectionUrl => valueFor('RTC_MEDIA_CONNECTION_URL');
  String get launchTarget => launchIdentity['launchTarget'] ?? '';
  String get effectiveLaunchManifestDigest =>
      launchIdentity['effectiveLaunchManifestDigest'] ?? '';

  String get launchMode {
    final value = valueFor('QWQ_APP_LAUNCH_MODE');
    return value.isEmpty ? 'unknown' : value;
  }

  String get launchPolicy {
    final value = valueFor('APP_LAUNCH_POLICY');
    return value.isEmpty ? 'unknown' : value;
  }

  bool get isValidAppRuntimeEnv =>
      appRuntimeEnv == 'alpha' ||
      appRuntimeEnv == 'beta' ||
      appRuntimeEnv == 'gamma' ||
      appRuntimeEnv == 'prod';

  List<String> get missingRequiredDefineKeys =>
      RuntimePackageValidator.invalidRuntimePackageKeys(
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
        launchPolicy: launchPolicy,
        launchTarget: launchTarget,
        effectiveLaunchManifestDigest: effectiveLaunchManifestDigest,
        enforceNativeLaunchBinding: enforceNativeLaunchBinding,
        nativeDriftKeys: driftKeys,
        forbiddenInputKeys: forbiddenInputKeys,
      );

  Map<String, String> get runtimeDefineSummary {
    if (shouldLoadNativeRuntimePackage && !nativeRuntimePackageHydrated) {
      return const <String, String>{
        'runtimeEnv': 'unknown',
        'launchMode': 'unknown',
        'configurationState': 'pending_native',
        'missingKeys': '',
      };
    }
    final invalid = missingRequiredDefineKeys;
    return <String, String>{
      'runtimeEnv': appRuntimeEnv.isEmpty ? 'unknown' : appRuntimeEnv,
      'launchMode': launchMode,
      'launchPolicy': launchPolicy,
      'configurationState': invalid.isEmpty ? 'complete' : 'invalid',
      if (launchTarget.isNotEmpty) 'launchTarget': launchTarget,
      if (effectiveLaunchManifestDigest.isNotEmpty)
        'effectiveLaunchManifestDigest': effectiveLaunchManifestDigest,
      'missingKeys': invalid.join(','),
    };
  }
}

final class RuntimePackageResolver {
  const RuntimePackageResolver._();

  static ResolvedRuntimePackage resolve({
    required Map<String, String> nativeValues,
    required Map<String, String> compiledPackage,
    required bool nativeRuntimePackageHydrated,
    bool enforceNativeLaunchBinding = true,
  }) {
    final compiled = <String, String>{
      for (final key in runtimePackageAllowedKeys)
        key: (compiledPackage[key] ?? '').trim(),
    };
    final native = <String, String>{
      for (final key in runtimePackageAllowedKeys)
        if ((nativeValues[key] ?? '').trim().isNotEmpty)
          key: nativeValues[key]!.trim(),
    };
    final compiledPackageIsEmpty = compiled.values.every(
      (value) => value.isEmpty,
    );
    final selected = compiledPackageIsEmpty ? native : compiled;
    final launchIdentity = <String, String>{
      for (final key in launchIdentityKeys)
        if ((nativeValues[key] ?? '').trim().isNotEmpty)
          key: nativeValues[key]!.trim(),
    };
    final driftKeys =
        compiledPackageIsEmpty ||
            !nativeRuntimePackageHydrated ||
            !enforceNativeLaunchBinding
        ? const <String>[]
        : runtimePackageAllowedKeys
              .where((key) => native[key] != compiled[key])
              .toList();
    final forbiddenInputKeys = <String>{
      for (final package in <Map<String, String>>[
        compiledPackage,
        nativeValues,
      ])
        for (final key in runtimePackageForbiddenContentKeys)
          if ((package[key] ?? '').trim().isNotEmpty) key,
    };
    return ResolvedRuntimePackage(
      source: compiledPackageIsEmpty
          ? RuntimePackageSource.native
          : RuntimePackageSource.compileTime,
      values: selected,
      launchIdentity: launchIdentity,
      driftKeys: driftKeys,
      forbiddenInputKeys: forbiddenInputKeys,
      nativeRuntimePackageHydrated: nativeRuntimePackageHydrated,
      enforceNativeLaunchBinding: enforceNativeLaunchBinding,
    );
  }
}

final class RuntimePackageValidator {
  const RuntimePackageValidator._();

  static const String testLiveLaunchPolicy = 'test_live';
  static const String prodReleaseLaunchPolicy = 'prod_release';
  static final RegExp _sha256Identity = RegExp(r'^sha256:[0-9a-f]{64}$');

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
    List<String> forbiddenInputKeys = const <String>[],
  }) {
    final invalid = <String>[
      ...invalidRuntimeEndpointKeys(
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
      ),
      if (launchPolicy != testLiveLaunchPolicy &&
          launchPolicy != prodReleaseLaunchPolicy)
        'APP_LAUNCH_POLICY',
      if (launchPolicy == testLiveLaunchPolicy && runtimeEnv == 'prod')
        'APP_LAUNCH_POLICY',
      if (launchPolicy == prodReleaseLaunchPolicy && runtimeEnv != 'prod')
        'APP_LAUNCH_POLICY',
      if (launchTarget.isNotEmpty &&
          launchTargetEnvironment[launchTarget] != runtimeEnv)
        'launchTarget',
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
      ...forbiddenInputKeys,
      for (final key in nativeDriftKeys) 'NATIVE_RUNTIME_PACKAGE.$key',
    ];
    return List<String>.unmodifiable(<String>{...invalid});
  }

  static List<String> invalidRuntimeEndpointKeys({
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
    final invalid = <String>[
      if (runtimeEnv != 'alpha' &&
          runtimeEnv != 'beta' &&
          runtimeEnv != 'gamma' &&
          runtimeEnv != 'prod')
        'APP_RUNTIME_ENV',
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
    ];
    if (invalid.isNotEmpty) {
      return List<String>.unmodifiable(<String>{...invalid});
    }
    final publicWeb = Uri.parse(publicWebBaseUrl);
    final legal = Uri.parse(legalBaseUrl);
    final appDownload = Uri.parse(appDownloadBaseUrl);
    final mediaAvatar = Uri.parse(mediaAvatarCdnBaseUrl);
    final mediaImage = Uri.parse(mediaImageCdnBaseUrl);
    final mediaVideo = Uri.parse(mediaVideoCdnBaseUrl);
    final mediaUpload = Uri.parse(mediaUploadBaseUrl);
    if (!_sameOrigin(publicWeb, legal) ||
        legal.path != _joinBasePath(publicWeb.path, 'legal')) {
      invalid.add('APP_LEGAL_BASE_URL');
    }
    if (!_sameOrigin(mediaAvatar, mediaImage) ||
        !_sameOrigin(mediaImage, mediaVideo) ||
        mediaAvatar.path != '/media/avatar' ||
        mediaImage.path != '/media/image' ||
        mediaVideo.path != '/media/video') {
      invalid.addAll(<String>[
        'MEDIA_AVATAR_CDN_BASE_URL',
        'MEDIA_IMAGE_CDN_BASE_URL',
        'MEDIA_VIDEO_CDN_BASE_URL',
      ]);
    }
    if (!_sameOrigin(appDownload, mediaImage) ||
        appDownload.path != '/download') {
      invalid.add('APP_DOWNLOAD_BASE_URL');
    }
    if (_sameOrigin(mediaUpload, mediaImage) || mediaUpload.path.isNotEmpty) {
      invalid.add('MEDIA_UPLOAD_BASE_URL');
    }
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

  static bool _sameOrigin(Uri left, Uri right) =>
      left.scheme.toLowerCase() == right.scheme.toLowerCase() &&
      left.host.toLowerCase() == right.host.toLowerCase() &&
      left.port == right.port;

  static String _joinBasePath(String basePath, String child) {
    final normalized = basePath.replaceFirst(RegExp(r'/+$'), '');
    return '$normalized/$child';
  }
}
