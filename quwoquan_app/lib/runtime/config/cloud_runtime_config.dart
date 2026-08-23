import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';

class CloudRuntimeConfigurationException implements Exception {
  CloudRuntimeConfigurationException({
    this.reason = 'runtime-package-invalid',
    this.source = 'signed-runtime-package',
    this.runtimeEnv = '',
    Iterable<String> invalidKeys = const <String>[],
  }) : invalidKeys = List<String>.unmodifiable(
         (invalidKeys.toSet().toList()..sort()),
       );

  final String reason;
  final String source;
  final String runtimeEnv;
  final List<String> invalidKeys;

  @override
  String toString() =>
      'CloudRuntimeConfigurationException(reason: $reason, '
      'invalidKeys: ${invalidKeys.join(',')})';
}

abstract final class CloudRuntimeConfig {
  static const String apiPath = '/graphql';
  static const String webRuntimeConfigPackagePath =
      '/runtime-config-package.json';

  static final RegExp _sha256Identity = RegExp(r'^sha256:[0-9a-f]{64}$');
  static ResolvedRuntimePackage? _resolvedPackage;
  static String? _verifiedRuntimeConfigPackageDigest;
  static String? _verifiedRuntimeConfigTrustEnvelopeDigest;
  static String? _effectiveLaunchManifestDigest;

  static bool get isHydrated => _resolvedPackage != null;

  static String get appEnvironment => _requiredPackage().environment;

  static String get buildProfile => _requiredPackage().buildProfile;

  static String get launchTarget => _requiredPackage().target;

  static String get appLaunchPolicy => _requiredPackage().launchPolicy;

  static String get appInstanceId =>
      const String.fromEnvironment('APP_INSTANCE_ID', defaultValue: 'unknown');

  static String get appRuntimeEnv => appEnvironment;

  static String get gatewayBaseUrl => _runtimeValue('gatewayBaseUrl');

  static String get cloudGatewayBaseUrl => gatewayBaseUrl;

  static String get realtimeConnectionUrl => _runtimeValue('realtimeBaseUrl');

  static String get publicWebBaseUrl => _runtimeValue('publicWebBaseUrl');

  static String get appDownloadBaseUrl => _runtimeValue('appDownloadBaseUrl');

  static String get legalBaseUrl => _runtimeValue('legalBaseUrl');

  static String get mediaAvatarCdnBaseUrl =>
      _runtimeValue('mediaAvatarCdnBaseUrl');

  static String get mediaImageCdnBaseUrl =>
      _runtimeValue('mediaImageCdnBaseUrl');

  static String get mediaVideoCdnBaseUrl =>
      _runtimeValue('mediaVideoCdnBaseUrl');

  static String get mediaUploadBaseUrl => _runtimeValue('mediaUploadBaseUrl');

  static String get rtcMediaConnectionUrl =>
      _runtimeValue('rtcMediaConnectionUrl');

  static String get webAppAndroidDownloadUrl => appDownloadBaseUrl;

  static String get webAppIosDownloadUrl => appDownloadBaseUrl;

  static String get webAppMobileDownloadUrl => appDownloadBaseUrl;

  static String get launchMode => 'external_runtime_package';

  static String? get effectiveLaunchManifestDigest {
    _requiredPackage();
    return _effectiveLaunchManifestDigest;
  }

  static String get runtimeConfigPackageDigest =>
      _verifiedRuntimeConfigPackageDigest ?? _canonicalPackageDigest();

  static String? get runtimeConfigTrustEnvelopeDigest {
    _requiredPackage();
    return _verifiedRuntimeConfigTrustEnvelopeDigest;
  }

  static String get runtimeConfigPayloadDigest =>
      _requiredPackage().payloadDigest;

  static String get graphqlEndpoint => '$gatewayBaseUrl$apiPath';

  static String get targetEnvironment => appEnvironment;

  static Future<void> hydrateFromNativeRuntimePackage({
    NativeRuntimeConfigBridge bridge = const NativeRuntimeConfigBridge(),
    RuntimePackageResolver? resolver,
    String? expectedTarget,
  }) async {
    try {
      final runtimeConfig = await bridge.readRuntimePackage();
      final runtimePackage = _runtimePackageFromBridge(runtimeConfig);
      final trustedTarget = expectedTarget ?? _trustedTarget(runtimeConfig);
      final trustedBuildProfile = _trustedBuildProfile(runtimeConfig);
      final trustedPublicKeys = _trustedPublicKeys(runtimeConfig);
      final resolvedPackage = await (resolver ?? RuntimePackageResolver())
          .resolve(
            runtimePackage: runtimePackage,
            expectedTarget: trustedTarget,
            trustedBuildProfile: trustedBuildProfile,
            trustedPublicKeys: trustedPublicKeys,
          );
      final verifiedIdentity = _verifiedIdentity(
        runtimeConfig,
        runtimePackage: runtimePackage,
      );
      _resolvedPackage = resolvedPackage;
      _verifiedRuntimeConfigPackageDigest = verifiedIdentity?.packageDigest;
      _verifiedRuntimeConfigTrustEnvelopeDigest =
          verifiedIdentity?.trustEnvelopeDigest;
      _effectiveLaunchManifestDigest =
          verifiedIdentity?.effectiveLaunchManifestDigest;
    } on NativeRuntimeConfigReadException catch (error) {
      _clearHydratedState();
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-package-read-${error.reason.name}',
        invalidKeys: const <String>['runtimeConfigPackage'],
      );
    } on RuntimePackageValidationException catch (error) {
      _clearHydratedState();
      throw CloudRuntimeConfigurationException(
        reason: error.reason,
        invalidKeys: error.invalidKeys,
      );
    } on CloudRuntimeConfigurationException {
      _clearHydratedState();
      rethrow;
    } on Object {
      _clearHydratedState();
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-package-unexpected-failure',
        invalidKeys: const <String>['runtimeConfigPackage'],
      );
    }
  }

  static void validateRequiredEndpoints() {
    final invalidKeys = <String>{};
    for (final entry in <String, String>{
      'gatewayBaseUrl': gatewayBaseUrl,
      'realtimeBaseUrl': realtimeConnectionUrl,
      'publicWebBaseUrl': publicWebBaseUrl,
      'appDownloadBaseUrl': appDownloadBaseUrl,
      'legalBaseUrl': legalBaseUrl,
      'mediaAvatarCdnBaseUrl': mediaAvatarCdnBaseUrl,
      'mediaImageCdnBaseUrl': mediaImageCdnBaseUrl,
      'mediaVideoCdnBaseUrl': mediaVideoCdnBaseUrl,
      'mediaUploadBaseUrl': mediaUploadBaseUrl,
      'rtcMediaConnectionUrl': rtcMediaConnectionUrl,
    }.entries) {
      final uri = Uri.tryParse(entry.value);
      final validScheme =
          entry.key == 'realtimeBaseUrl' || entry.key == 'rtcMediaConnectionUrl'
          ? uri?.scheme == 'wss'
          : uri?.scheme == 'https';
      if (uri == null || !validScheme || uri.host.isEmpty) {
        invalidKeys.add(entry.key);
      }
    }
    if (invalidKeys.isNotEmpty) {
      throw CloudRuntimeConfigurationException(
        reason: 'required-endpoint-invalid',
        invalidKeys: invalidKeys,
      );
    }
  }

  static void validateRuntimePackage() => validateRequiredEndpoints();

  static Map<String, String> get runtimeDefineSummary {
    final resolvedPackage = _resolvedPackage;
    if (resolvedPackage == null) {
      return const <String, String>{
        'configurationSource': 'signed-runtime-package',
        'configurationState': 'missing',
      };
    }
    return resolvedPackage.runtimeDefineSummary;
  }

  static RuntimeFailure? runtimeAvailabilityFailure() {
    final summary = runtimeDefineSummary;
    final configurationState = summary['configurationState'] ?? 'invalid';
    if (configurationState == 'complete') {
      return null;
    }
    final errorCode = OpsEventRecordErrorCode.startupConfigurationInvalid;
    return RuntimeFailure(
      code: errorCode.code,
      semanticReason: errorCode.name,
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'runtime.configuration',
        functionModule: 'runtime_package_preflight',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'configurationSource',
            value: summary['configurationSource'] ?? 'signed-runtime-package',
          ),
          RuntimeContextAttribute(
            key: 'configurationState',
            value: configurationState,
          ),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'fullPage',
      ),
    );
  }

  static ResolvedRuntimePackage _requiredPackage() {
    final resolvedPackage = _resolvedPackage;
    if (resolvedPackage == null) {
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-package-not-hydrated',
        invalidKeys: const <String>['runtimeConfigPackage'],
      );
    }
    return resolvedPackage;
  }

  static void _clearHydratedState() {
    _resolvedPackage = null;
    _verifiedRuntimeConfigPackageDigest = null;
    _verifiedRuntimeConfigTrustEnvelopeDigest = null;
    _effectiveLaunchManifestDigest = null;
  }

  static String _canonicalPackageDigest() {
    final package = _requiredPackage();
    final packageDocument = <String, Object?>{
      ...package.package.signedPayloadMap(),
      'signature': package.package.signature,
    };
    return 'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(packageDocument)))}';
  }

  static String _runtimeValue(String key) {
    try {
      return _requiredPackage().runtimeValue(key);
    } on RuntimePackageValidationException catch (error) {
      throw CloudRuntimeConfigurationException(
        reason: error.reason,
        invalidKeys: error.invalidKeys,
      );
    }
  }

  static _VerifiedRuntimeConfigIdentity? _verifiedIdentity(
    Map<String, Object?> bridgeValue, {
    required Map<String, Object?> runtimePackage,
  }) {
    if (!bridgeValue.containsKey('package')) {
      return null;
    }
    final packageDigest = bridgeValue['runtimeConfigPackageDigest'];
    final trustDigest = bridgeValue['runtimeConfigTrustEnvelopeDigest'];
    final manifestDigest = bridgeValue['effectiveLaunchManifestDigest'];
    final invalidKeys = <String>{};
    for (final entry in <String, Object?>{
      'runtimeConfigPackageDigest': packageDigest,
      'runtimeConfigTrustEnvelopeDigest': trustDigest,
      'effectiveLaunchManifestDigest': manifestDigest,
    }.entries) {
      if (entry.value is! String ||
          !_sha256Identity.hasMatch(entry.value! as String)) {
        invalidKeys.add(entry.key);
      }
    }
    if (packageDigest is String &&
        _sha256Identity.hasMatch(packageDigest) &&
        packageDigest !=
            'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(runtimePackage)))}') {
      invalidKeys.add('runtimeConfigPackageDigest');
    }
    final trustDocument = <String, Object?>{
      'buildProfile': bridgeValue['trustedBuildProfile'],
      'schema': 'app-runtime-config-trust',
      'schemaVersion': runtimePackageSchemaVersion,
      'signatureAlgorithm': 'ed25519',
      'trustedPublicKeys': bridgeValue['trustedPublicKeys'],
    };
    if (trustDigest is String &&
        _sha256Identity.hasMatch(trustDigest) &&
        trustDigest !=
            'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(trustDocument)))}') {
      invalidKeys.add('runtimeConfigTrustEnvelopeDigest');
    }
    if (invalidKeys.isNotEmpty) {
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-verified-identity-invalid',
        invalidKeys: invalidKeys,
      );
    }
    return _VerifiedRuntimeConfigIdentity(
      packageDigest: packageDigest as String,
      trustEnvelopeDigest: trustDigest as String,
      effectiveLaunchManifestDigest: manifestDigest as String,
    );
  }

  static Map<String, Object?> _runtimePackageFromBridge(
    Map<String, Object?> bridgeValue,
  ) {
    final package = bridgeValue['package'];
    if (package == null) {
      return bridgeValue;
    }
    final invalidKeys = <String>{
      ...bridgeValue.keys.where(
        (key) => !runtimePackageTrustEnvelopeKeys.contains(key),
      ),
      ...runtimePackageTrustEnvelopeKeys.where(
        (key) => !bridgeValue.containsKey(key),
      ),
    };
    if (invalidKeys.isNotEmpty) {
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-trust-envelope-invalid',
        invalidKeys: invalidKeys,
      );
    }
    if (package is! Map) {
      throw CloudRuntimeConfigurationException(
        reason: 'runtime-package-invalid',
        invalidKeys: const <String>['package'],
      );
    }
    return Map<String, Object?>.from(package);
  }

  static Map<String, String> _trustedPublicKeys(
    Map<String, Object?> bridgeValue,
  ) {
    final package = _runtimePackageFromBridge(bridgeValue);
    final raw = bridgeValue.containsKey('package')
        ? bridgeValue['trustedPublicKeys']
        : package['trustedPublicKeys'];
    if (raw is! Map || raw.isEmpty) {
      throw CloudRuntimeConfigurationException(
        reason: 'trusted-public-keys-invalid',
        invalidKeys: const <String>['trustedPublicKeys'],
      );
    }
    final trustedKeys = <String, String>{};
    for (final entry in raw.entries) {
      if (entry.key is! String ||
          entry.value is! String ||
          (entry.key as String).trim().isEmpty ||
          (entry.value as String).trim().isEmpty) {
        throw CloudRuntimeConfigurationException(
          reason: 'trusted-public-keys-invalid',
          invalidKeys: const <String>['trustedPublicKeys'],
        );
      }
      final keyId = entry.key as String;
      final encodedKey = entry.value as String;
      try {
        decodeStrictRuntimePackageBase64(
          encodedKey,
          key: 'trustedPublicKeys',
          expectedLength: 32,
        );
      } on RuntimePackageValidationException catch (error) {
        throw CloudRuntimeConfigurationException(
          reason: error.reason,
          invalidKeys: error.invalidKeys,
        );
      }
      trustedKeys[keyId] = encodedKey;
    }
    return Map<String, String>.unmodifiable(trustedKeys);
  }

  static String _trustedTarget(Map<String, Object?> bridgeValue) {
    final package = _runtimePackageFromBridge(bridgeValue);
    final target = bridgeValue.containsKey('package')
        ? bridgeValue['trustedTarget']
        : package['target'];
    if (target is! String || !launchTargetEnvironment.containsKey(target)) {
      throw CloudRuntimeConfigurationException(
        reason: 'trusted-target-invalid',
        invalidKeys: const <String>['trustedTarget'],
      );
    }
    return target;
  }

  static String _trustedBuildProfile(Map<String, Object?> bridgeValue) {
    final package = _runtimePackageFromBridge(bridgeValue);
    final profile = bridgeValue.containsKey('package')
        ? bridgeValue['trustedBuildProfile']
        : package['buildProfile'];
    if (profile is! String ||
        !const <String>{'nonprod', 'prod'}.contains(profile)) {
      throw CloudRuntimeConfigurationException(
        reason: 'trusted-build-profile-invalid',
        invalidKeys: const <String>['trustedBuildProfile'],
      );
    }
    return profile;
  }
}

final class _VerifiedRuntimeConfigIdentity {
  const _VerifiedRuntimeConfigIdentity({
    required this.packageDigest,
    required this.trustEnvelopeDigest,
    required this.effectiveLaunchManifestDigest,
  });

  final String packageDigest;
  final String trustEnvelopeDigest;
  final String effectiveLaunchManifestDigest;
}
