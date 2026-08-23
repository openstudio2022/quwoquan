import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:crypto/crypto.dart' as crypto;

const String runtimePackageSchema = 'app-runtime-config-package';
const String runtimePackageSchemaVersion = '1';
const String runtimePackageTestLiveLaunchPolicy = 'test_live';
const String runtimePackageProdReleaseLaunchPolicy = 'prod_release';
const Duration runtimePackageMaximumLifetime = Duration(hours: 24);
const Duration runtimePackageMaximumFutureSkew = Duration(minutes: 5);

const Set<String> runtimePackageValueKeys = <String>{
  'appRuntimeEnv',
  'gatewayBaseUrl',
  'legalBaseUrl',
  'publicWebBaseUrl',
  'appDownloadBaseUrl',
  'realtimeBaseUrl',
  'mediaAvatarCdnBaseUrl',
  'mediaImageCdnBaseUrl',
  'mediaVideoCdnBaseUrl',
  'mediaUploadBaseUrl',
  'rtcMediaConnectionUrl',
};

const Set<String> runtimePackageEndpointKeys = <String>{
  'gatewayBaseUrl',
  'legalBaseUrl',
  'publicWebBaseUrl',
  'appDownloadBaseUrl',
  'realtimeBaseUrl',
  'mediaAvatarCdnBaseUrl',
  'mediaImageCdnBaseUrl',
  'mediaVideoCdnBaseUrl',
  'mediaUploadBaseUrl',
  'rtcMediaConnectionUrl',
};

const Set<String> runtimePackageEnvelopeKeys = <String>{
  'schema',
  'schemaVersion',
  'environment',
  'buildProfile',
  'target',
  'launchPolicy',
  'issuedAt',
  'expiresAt',
  'sourceGitSha',
  'sourceTreeDigest',
  'runtime',
  'payloadDigest',
  'signatureAlgorithm',
  'signatureKeyId',
  'trustedPublicKeys',
  'signature',
};

const Set<String> runtimePackageTrustEnvelopeKeys = <String>{
  'package',
  'trustedBuildProfile',
  'trustedTarget',
  'trustedPublicKeys',
  'runtimeConfigPackageDigest',
  'runtimeConfigTrustEnvelopeDigest',
  'effectiveLaunchManifestDigest',
};

const Set<String> runtimePackageForbiddenContentKeys = <String>{
  'APP_CONTENT_BUNDLE_ID',
  'APP_CONTENT_RELEASE_ID',
  'CONTENT_RELEASE_ID',
  'CONTENT_RELEASE',
  'CONTENT_BUNDLE_ID',
  'CONTENT_DATA_RELEASE_ID',
  'CONTENT_DATA_RELEASE_PATH',
  'CONTENT_DATA_CHECKSUM',
  'CONTENT_DATA_INDEX_CHECKSUM',
  'CONTENT_VERSION',
  'RECOMMENDATION_POLICY_RELEASE_ID',
  'RECOMMENDATION_POLICY_ID',
  'RECOMMENDATION_POLICY_VERSION',
  'CONTENT_IMPORT_RELEASE_ID',
  'CONTENT_IMPORT_CHECKSUM',
  'CONTENT_IMPORT_PATH',
  'GRAY_STAGE',
  'ROLLOUT_STAGE',
  'CHANNEL',
  'APP_CHANNEL',
  'SECRET',
  'SECRETS',
};

class RuntimePackageValidationException implements Exception {
  RuntimePackageValidationException({
    required this.reason,
    Iterable<String> invalidKeys = const <String>[],
  }) : invalidKeys = List<String>.unmodifiable(
         (invalidKeys.toSet().toList()..sort()),
       );

  final String reason;
  final List<String> invalidKeys;

  @override
  String toString() =>
      'RuntimePackageValidationException(reason: $reason, '
      'invalidKeys: ${invalidKeys.join(',')})';
}

class RuntimeConfigPackage {
  const RuntimeConfigPackage({
    required this.schema,
    required this.schemaVersion,
    required this.environment,
    required this.buildProfile,
    required this.target,
    required this.launchPolicy,
    required this.issuedAt,
    required this.expiresAt,
    required this.sourceGitSha,
    required this.sourceTreeDigest,
    required this.runtimeValues,
    required this.payloadDigest,
    required this.signatureKeyId,
    required this.trustedPublicKeys,
    required this.signature,
  });

  final String schema;
  final String schemaVersion;
  final String environment;
  final String buildProfile;
  final String target;
  final String launchPolicy;
  final DateTime issuedAt;
  final DateTime expiresAt;
  final String sourceGitSha;
  final String sourceTreeDigest;
  final Map<String, String> runtimeValues;
  final String payloadDigest;
  final String signatureKeyId;
  final Map<String, String> trustedPublicKeys;
  final String signature;

  factory RuntimeConfigPackage.fromMap(Map<String, Object?> input) {
    final invalidKeys = <String>{
      ...input.keys.where((key) => !runtimePackageEnvelopeKeys.contains(key)),
    };
    for (final key in runtimePackageEnvelopeKeys) {
      if (!input.containsKey(key)) {
        invalidKeys.add(key);
      }
    }
    if (invalidKeys.isNotEmpty) {
      throw RuntimePackageValidationException(
        reason: 'package-shape-invalid',
        invalidKeys: invalidKeys,
      );
    }

    String requiredString(String key) {
      final value = input[key];
      if (value is! String || value.trim().isEmpty) {
        throw RuntimePackageValidationException(
          reason: 'field-invalid',
          invalidKeys: <String>[key],
        );
      }
      return value.trim();
    }

    final rawRuntimeValues = input['runtime'];
    if (rawRuntimeValues is! Map) {
      throw RuntimePackageValidationException(
        reason: 'field-invalid',
        invalidKeys: const <String>['runtime'],
      );
    }
    final runtimeValues = <String, String>{};
    for (final entry in rawRuntimeValues.entries) {
      if (entry.key is! String || entry.value is! String) {
        throw RuntimePackageValidationException(
          reason: 'runtime-values-invalid',
          invalidKeys: const <String>['runtime'],
        );
      }
      runtimeValues[entry.key as String] = entry.value as String;
    }

    DateTime requiredTimestamp(String key) {
      final raw = requiredString(key);
      final parsed = DateTime.tryParse(raw);
      if (parsed == null ||
          !raw.endsWith('Z') ||
          parsed.timeZoneOffset != Duration.zero) {
        throw RuntimePackageValidationException(
          reason: 'timestamp-invalid',
          invalidKeys: <String>[key],
        );
      }
      final timestamp = parsed.toUtc();
      if (_canonicalTimestamp(timestamp) != raw) {
        throw RuntimePackageValidationException(
          reason: 'timestamp-invalid',
          invalidKeys: <String>[key],
        );
      }
      return timestamp;
    }

    final algorithm = requiredString('signatureAlgorithm');
    if (algorithm != 'ed25519') {
      throw RuntimePackageValidationException(
        reason: 'signature-algorithm-invalid',
        invalidKeys: const <String>['signatureAlgorithm'],
      );
    }

    final rawTrustedPublicKeys = input['trustedPublicKeys'];
    if (rawTrustedPublicKeys is! Map || rawTrustedPublicKeys.isEmpty) {
      throw RuntimePackageValidationException(
        reason: 'trusted-public-keys-invalid',
        invalidKeys: const <String>['trustedPublicKeys'],
      );
    }
    final trustedPublicKeys = <String, String>{};
    for (final entry in rawTrustedPublicKeys.entries) {
      if (entry.key is! String ||
          entry.value is! String ||
          (entry.key as String).trim().isEmpty ||
          (entry.value as String).trim().isEmpty) {
        throw RuntimePackageValidationException(
          reason: 'trusted-public-keys-invalid',
          invalidKeys: const <String>['trustedPublicKeys'],
        );
      }
      trustedPublicKeys[entry.key as String] = entry.value as String;
    }

    return RuntimeConfigPackage(
      schema: requiredString('schema'),
      schemaVersion: requiredString('schemaVersion'),
      environment: requiredString('environment'),
      buildProfile: requiredString('buildProfile'),
      target: requiredString('target'),
      launchPolicy: requiredString('launchPolicy'),
      issuedAt: requiredTimestamp('issuedAt'),
      expiresAt: requiredTimestamp('expiresAt'),
      sourceGitSha: requiredString('sourceGitSha'),
      sourceTreeDigest: requiredString('sourceTreeDigest'),
      runtimeValues: Map<String, String>.unmodifiable(runtimeValues),
      payloadDigest: requiredString('payloadDigest'),
      signatureKeyId: requiredString('signatureKeyId'),
      trustedPublicKeys: Map<String, String>.unmodifiable(trustedPublicKeys),
      signature: requiredString('signature'),
    );
  }

  Map<String, Object?> canonicalPayloadMap() => <String, Object?>{
    'buildProfile': buildProfile,
    'environment': environment,
    'expiresAt': _canonicalTimestamp(expiresAt),
    'issuedAt': _canonicalTimestamp(issuedAt),
    'launchPolicy': launchPolicy,
    'runtime': runtimeValues,
    'schema': schema,
    'schemaVersion': schemaVersion,
    'signatureAlgorithm': 'ed25519',
    'signatureKeyId': signatureKeyId,
    'sourceGitSha': sourceGitSha,
    'sourceTreeDigest': sourceTreeDigest,
    'target': target,
    'trustedPublicKeys': trustedPublicKeys,
  };

  Map<String, Object?> digestPayloadMap() => <String, Object?>{
    ...canonicalPayloadMap(),
    'payloadDigest': '',
  };

  Map<String, Object?> signedPayloadMap() => <String, Object?>{
    ...canonicalPayloadMap(),
    'payloadDigest': payloadDigest,
  };
}

class ResolvedRuntimePackage {
  const ResolvedRuntimePackage({required this.package, required this.values});

  final RuntimeConfigPackage package;
  final Map<String, String> values;

  String get environment => package.environment;
  String get buildProfile => package.buildProfile;
  String get target => package.target;
  String get launchPolicy => package.launchPolicy;
  String get sourceGitSha => package.sourceGitSha;
  String get sourceTreeDigest => package.sourceTreeDigest;
  String get payloadDigest => package.payloadDigest;
  String get signatureKeyId => package.signatureKeyId;

  String runtimeValue(String key) {
    final value = values[key];
    if (value == null || value.isEmpty) {
      throw RuntimePackageValidationException(
        reason: 'runtime-value-missing',
        invalidKeys: <String>[key],
      );
    }
    return value;
  }

  Map<String, String> get runtimeDefineSummary => <String, String>{
    'configurationSource': 'signed-runtime-package',
    'configurationState': 'complete',
    'runtimeEnv': environment,
    'environment': environment,
    'buildProfile': buildProfile,
    'target': target,
    'launchMode': 'external_runtime_package',
    'launchPolicy': launchPolicy,
    'payloadDigest': payloadDigest,
    'signatureKeyId': signatureKeyId,
    'sourceGitSha': sourceGitSha,
    'sourceTreeDigest': sourceTreeDigest,
  };
}

class RuntimePackageResolver {
  RuntimePackageResolver({
    DateTime Function()? now,
    Ed25519? signatureAlgorithm,
  }) : _now = now ?? (() => DateTime.now().toUtc()),
       _signatureAlgorithm = signatureAlgorithm ?? Ed25519();

  final DateTime Function() _now;
  final Ed25519 _signatureAlgorithm;

  Future<ResolvedRuntimePackage> resolve({
    required Map<String, Object?> runtimePackage,
    required String expectedTarget,
    required String trustedBuildProfile,
    required Map<String, String> trustedPublicKeys,
  }) async {
    final package = RuntimeConfigPackage.fromMap(runtimePackage);
    final invalidKeys = <String>{};

    if (package.schema != runtimePackageSchema) {
      invalidKeys.add('schema');
    }
    if (package.schemaVersion != runtimePackageSchemaVersion) {
      invalidKeys.add('schemaVersion');
    }
    if (package.buildProfile != trustedBuildProfile) {
      invalidKeys.add('buildProfile');
    }
    if (!_environmentMatchesProfile(
      environment: package.environment,
      buildProfile: package.buildProfile,
    )) {
      invalidKeys.addAll(const <String>['environment', 'buildProfile']);
    }
    final expectedEnvironment = launchTargetEnvironment[package.target];
    if (expectedEnvironment == null ||
        package.target != expectedTarget ||
        package.environment != expectedEnvironment) {
      invalidKeys.addAll(const <String>['target', 'environment']);
    }
    final expectedLaunchPolicy = package.environment == 'prod'
        ? runtimePackageProdReleaseLaunchPolicy
        : runtimePackageTestLiveLaunchPolicy;
    if (package.launchPolicy != expectedLaunchPolicy) {
      invalidKeys.add('launchPolicy');
    }
    if (package.runtimeValues['appRuntimeEnv'] != package.environment) {
      invalidKeys.add('appRuntimeEnv');
    }
    if (!_sourceGitShaPattern.hasMatch(package.sourceGitSha)) {
      invalidKeys.add('sourceGitSha');
    }
    if (!_sourceTreeDigestPattern.hasMatch(package.sourceTreeDigest)) {
      invalidKeys.add('sourceTreeDigest');
    }
    _collectRuntimeValueInvalidKeys(package.runtimeValues, invalidKeys);

    final now = _now().toUtc();
    if (package.issuedAt.isAfter(now.add(runtimePackageMaximumFutureSkew))) {
      invalidKeys.add('issuedAt');
    }
    if (!package.expiresAt.isAfter(now)) {
      invalidKeys.add('expiresAt');
    }
    final lifetime = package.expiresAt.difference(package.issuedAt);
    if (lifetime <= Duration.zero || lifetime > runtimePackageMaximumLifetime) {
      invalidKeys.addAll(const <String>['issuedAt', 'expiresAt']);
    }
    if (invalidKeys.isNotEmpty) {
      throw RuntimePackageValidationException(
        reason: 'package-claims-invalid',
        invalidKeys: invalidKeys,
      );
    }

    final digestPayload = canonicalJsonEncode(package.digestPayloadMap());
    final calculatedDigest =
        'sha256:${crypto.sha256.convert(utf8.encode(digestPayload))}';
    if (!_digestPattern.hasMatch(package.payloadDigest) ||
        package.payloadDigest != calculatedDigest) {
      throw RuntimePackageValidationException(
        reason: 'payload-digest-invalid',
        invalidKeys: const <String>['payloadDigest'],
      );
    }

    if (!_keyringsEqual(package.trustedPublicKeys, trustedPublicKeys)) {
      throw RuntimePackageValidationException(
        reason: 'trusted-public-keys-mismatch',
        invalidKeys: const <String>['trustedPublicKeys'],
      );
    }
    final encodedPublicKey = trustedPublicKeys[package.signatureKeyId];
    if (encodedPublicKey == null) {
      throw RuntimePackageValidationException(
        reason: 'signature-key-untrusted',
        invalidKeys: const <String>['signatureKeyId'],
      );
    }
    final publicKeyBytes = decodeStrictRuntimePackageBase64(
      encodedPublicKey,
      key: 'trustedPublicKeys',
      expectedLength: 32,
    );
    final signatureBytes = decodeStrictRuntimePackageBase64(
      package.signature,
      key: 'signature',
      expectedLength: 64,
    );
    final signedPayload = canonicalJsonEncode(package.signedPayloadMap());
    final verified = await _signatureAlgorithm.verify(
      utf8.encode(signedPayload),
      signature: Signature(
        signatureBytes,
        publicKey: SimplePublicKey(publicKeyBytes, type: KeyPairType.ed25519),
      ),
    );
    if (!verified) {
      throw RuntimePackageValidationException(
        reason: 'signature-invalid',
        invalidKeys: const <String>['signature'],
      );
    }

    return ResolvedRuntimePackage(
      package: package,
      values: Map<String, String>.unmodifiable(package.runtimeValues),
    );
  }
}

const Map<String, String> launchTargetEnvironment = <String, String>{
  'alpha-local': 'alpha',
  'beta-local': 'beta',
  'gamma-local': 'gamma',
  'prod-sim': 'prod',
  'prod-hosted': 'prod',
};
final RegExp _sourceGitShaPattern = RegExp(r'^[0-9a-f]{40}$');
final RegExp _digestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
final RegExp _sourceTreeDigestPattern = RegExp(
  r'^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$',
);
final RegExp _secretKeyPattern = RegExp(
  r'(secret|password|private.?key|access.?token|api.?key|credential)',
  caseSensitive: false,
);

bool _keyringsEqual(
  Map<String, String> packageKeyring,
  Map<String, String> trustedKeyring,
) {
  if (packageKeyring.length != trustedKeyring.length) {
    return false;
  }
  for (final entry in packageKeyring.entries) {
    if (trustedKeyring[entry.key] != entry.value) {
      return false;
    }
  }
  return true;
}

bool _environmentMatchesProfile({
  required String environment,
  required String buildProfile,
}) {
  if (buildProfile == 'nonprod') {
    return const <String>{'alpha', 'beta', 'gamma'}.contains(environment);
  }
  return buildProfile == 'prod' && environment == 'prod';
}

void _collectRuntimeValueInvalidKeys(
  Map<String, String> values,
  Set<String> invalidKeys,
) {
  invalidKeys.addAll(
    values.keys.where((key) => !runtimePackageValueKeys.contains(key)),
  );
  invalidKeys.addAll(
    runtimePackageValueKeys.where((key) => !values.containsKey(key)),
  );
  for (final entry in values.entries) {
    final key = entry.key;
    final value = entry.value.trim();
    if (runtimePackageForbiddenContentKeys.contains(key) ||
        _secretKeyPattern.hasMatch(key)) {
      invalidKeys.add(key);
      continue;
    }
    if (value.isEmpty) {
      invalidKeys.add(key);
      continue;
    }
    if (runtimePackageEndpointKeys.contains(key)) {
      final uri = Uri.tryParse(value);
      final validScheme =
          key == 'realtimeBaseUrl' || key == 'rtcMediaConnectionUrl'
          ? uri?.scheme == 'wss'
          : uri?.scheme == 'https';
      if (uri == null ||
          !validScheme ||
          uri.host.isEmpty ||
          uri.userInfo.isNotEmpty ||
          uri.hasQuery ||
          uri.hasFragment) {
        invalidKeys.add(key);
      }
    }
  }
}

List<int> decodeStrictRuntimePackageBase64(
  String encoded, {
  required String key,
  required int expectedLength,
}) {
  if (encoded.trim() != encoded ||
      encoded.isEmpty ||
      encoded.length % 4 != 0 ||
      !RegExp(r'^[A-Za-z0-9+/]+={0,2}$').hasMatch(encoded)) {
    throw RuntimePackageValidationException(
      reason: 'base64-invalid',
      invalidKeys: <String>[key],
    );
  }
  late final List<int> decoded;
  try {
    decoded = base64.decode(encoded);
  } on FormatException {
    throw RuntimePackageValidationException(
      reason: 'base64-invalid',
      invalidKeys: <String>[key],
    );
  }
  if (decoded.length != expectedLength || base64.encode(decoded) != encoded) {
    throw RuntimePackageValidationException(
      reason: 'base64-invalid',
      invalidKeys: <String>[key],
    );
  }
  return decoded;
}

String canonicalJsonEncode(Object? value) {
  Object? canonicalize(Object? current) {
    if (current is Map) {
      if (current.keys.any((key) => key is! String)) {
        throw RuntimePackageValidationException(
          reason: 'canonical-json-invalid',
          invalidKeys: const <String>['runtime'],
        );
      }
      final keys = current.keys.cast<String>().toList()..sort();
      return <String, Object?>{
        for (final key in keys) key: canonicalize(current[key]),
      };
    }
    if (current is List) {
      return current.map(canonicalize).toList(growable: false);
    }
    if (current == null ||
        current is String ||
        current is num ||
        current is bool) {
      return current;
    }
    throw RuntimePackageValidationException(
      reason: 'canonical-json-invalid',
      invalidKeys: const <String>['runtime'],
    );
  }

  return jsonEncode(canonicalize(value));
}

String _canonicalTimestamp(DateTime value) =>
    value.toUtc().toIso8601String().replaceFirst('.000Z', 'Z');
