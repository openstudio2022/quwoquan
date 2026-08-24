import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

const _now = '2026-08-22T12:00:00Z';

Future<Map<String, Object?>> _signedPackage({
  String environment = 'gamma',
  String buildProfile = 'nonprod',
  String target = 'gamma-local',
  String launchPolicy = runtimePackageTestLiveLaunchPolicy,
  bool deriveLaunchPolicy = false,
  String issuedAt = '2026-08-22T11:55:00Z',
  String expiresAt = '2026-08-22T13:00:00Z',
  Map<String, String>? runtime,
  SimpleKeyPair? signingKey,
  String signatureKeyId = 'nonprod-2026-01',
  String trustedKeyId = 'nonprod-2026-01',
}) async {
  final algorithm = Ed25519();
  final keyPair = signingKey ?? await algorithm.newKeyPair();
  final publicKey = await keyPair.extractPublicKey();
  final trustedPublicKeys = <String, String>{
    trustedKeyId: base64.encode(publicKey.bytes),
  };
  final payload = <String, Object?>{
    'buildProfile': buildProfile,
    'environment': environment,
    'expiresAt': expiresAt,
    'issuedAt': issuedAt,
    'launchPolicy': deriveLaunchPolicy
        ? '${environment}_release'
        : launchPolicy,
    'payloadDigest': '',
    'runtime': runtime ?? _runtimeValues(environment),
    'schema': runtimePackageSchema,
    'signatureAlgorithm': 'ed25519',
    'signatureKeyId': signatureKeyId,
    'sourceGitSha': 'a' * 40,
    'sourceTreeDigest': 'sha256:${'b' * 64}',
    'target': target,
    'trustedPublicKeys': trustedPublicKeys,
  };
  final digest = crypto.sha256
      .convert(utf8.encode(canonicalJsonEncode(payload)))
      .toString();
  payload['payloadDigest'] = 'sha256:$digest';
  final signature = await algorithm.sign(
    utf8.encode(canonicalJsonEncode(payload)),
    keyPair: keyPair,
  );
  final runtimePackage = <String, Object?>{
    ...payload,
    'signature': base64.encode(signature.bytes),
  };
  final trustDocument = <String, Object?>{
    'buildProfile': buildProfile,
    'schema': 'app-runtime-config-trust',
    'signatureAlgorithm': 'ed25519',
    'trustedPublicKeys': trustedPublicKeys,
  };
  return <String, Object?>{
    'package': runtimePackage,
    'trustedBuildProfile': buildProfile,
    'trustedTarget': target,
    'trustedPublicKeys': trustedPublicKeys,
    'runtimeConfigPackageDigest':
        'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(runtimePackage)))}',
    'runtimeConfigTrustEnvelopeDigest':
        'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(trustDocument)))}',
    'effectiveLaunchManifestDigest': 'sha256:${'c' * 64}',
  };
}

Map<String, String> _runtimeValues(String environment) => <String, String>{
  'appRuntimeEnv': environment,
  'gatewayBaseUrl': 'https://api.example.test',
  'legalBaseUrl': 'https://www.example.test/legal',
  'publicWebBaseUrl': 'https://www.example.test',
  'appDownloadBaseUrl': 'https://cdn.example.test/download',
  'realtimeBaseUrl': 'wss://api.example.test',
  'mediaAvatarCdnBaseUrl': 'https://cdn.example.test/media/avatar',
  'mediaImageCdnBaseUrl': 'https://cdn.example.test/media/image',
  'mediaVideoCdnBaseUrl': 'https://cdn.example.test/media/video',
  'mediaUploadBaseUrl': 'https://upload.example.test',
  'rtcMediaConnectionUrl': 'wss://rtc.example.test',
};

RuntimePackageResolver _resolver() =>
    RuntimePackageResolver(now: () => DateTime.parse(_now));

final class _EnvelopeClient implements RuntimeConfigChannelClient {
  const _EnvelopeClient(this.envelope);

  final Map<String, Object?> envelope;

  @override
  Future<Object?> invokeMethod(String method) async => envelope;
}

Future<ResolvedRuntimePackage> _resolve(
  Map<String, Object?> trustEnvelope, {
  String target = 'gamma-local',
  String trustedBuildProfile = 'nonprod',
}) => _resolver().resolve(
  runtimePackage: Map<String, Object?>.from(trustEnvelope['package']! as Map),
  expectedTarget: target,
  trustedBuildProfile: trustedBuildProfile,
  trustedPublicKeys: Map<String, String>.from(
    trustEnvelope['trustedPublicKeys']! as Map,
  ),
);

void main() {
  test('合法 Ed25519 runtime package 通过并成为唯一配置来源', () async {
    final resolved = await _resolve(await _signedPackage());

    expect(resolved.environment, 'gamma');
    expect(resolved.buildProfile, 'nonprod');
    expect(resolved.runtimeValue('gatewayBaseUrl'), 'https://api.example.test');
    expect(
      resolved.runtimeDefineSummary['configurationSource'],
      'signed-runtime-package',
    );
    expect(
      resolved.runtimeDefineSummary.values,
      isNot(contains('https://api.example.test')),
    );
    expect(
      () => resolved.runtimeValue('unknownRuntimeKey'),
      throwsA(
        isA<RuntimePackageValidationException>()
            .having((error) => error.reason, 'reason', 'runtime-value-missing')
            .having((error) => error.invalidKeys, 'invalidKeys', <String>[
              'unknownRuntimeKey',
            ]),
      ),
    );
  });

  test('篡改 payload 在 digest 校验处 fail closed', () async {
    final package = await _signedPackage();
    final payload = package['package']! as Map<String, Object?>;
    final runtime = Map<String, String>.from(payload['runtime']! as Map)
      ..['gatewayBaseUrl'] = 'https://tampered.example.test';
    payload['runtime'] = runtime;

    await expectLater(
      _resolve(package),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['payloadDigest']),
        ),
      ),
    );
  });

  test('错误 key id 与错误签名均拒绝', () async {
    final unknownKey = await _signedPackage(signatureKeyId: 'unknown');
    await expectLater(
      _resolve(unknownKey),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['signatureKeyId']),
        ),
      ),
    );

    final package = await _signedPackage();
    final payload = package['package']! as Map<String, Object?>;
    final signatureBytes = base64.decode(payload['signature']! as String);
    signatureBytes[0] ^= 1;
    payload['signature'] = base64.encode(signatureBytes);
    await expectLater(
      _resolve(package),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['signature']),
        ),
      ),
    );
  });

  test('package 自带 keyring 不能替代独立信任根', () async {
    final package = await _signedPackage();
    final wrongKey = await Ed25519().newKeyPair();
    final wrongPublicKey = await wrongKey.extractPublicKey();

    await expectLater(
      _resolver().resolve(
        runtimePackage: Map<String, Object?>.from(package['package']! as Map),
        expectedTarget: 'gamma-local',
        trustedBuildProfile: 'nonprod',
        trustedPublicKeys: <String, String>{
          'nonprod-2026-01': base64.encode(wrongPublicKey.bytes),
        },
      ),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['trustedPublicKeys']),
        ),
      ),
    );
  });

  test('过期、未来签发与过长 freshness 均拒绝', () async {
    for (final testCase in <Map<String, String>>[
      <String, String>{
        'issuedAt': '2026-08-22T10:00:00Z',
        'expiresAt': '2026-08-22T11:59:59Z',
        'invalid': 'expiresAt',
      },
      <String, String>{
        'issuedAt': '2026-08-22T12:06:00Z',
        'expiresAt': '2026-08-22T13:00:00Z',
        'invalid': 'issuedAt',
      },
      <String, String>{
        'issuedAt': '2026-08-21T00:00:00Z',
        'expiresAt': '2026-08-23T00:00:00Z',
        'invalid': 'expiresAt',
      },
    ]) {
      await expectLater(
        _resolve(
          await _signedPackage(
            issuedAt: testCase['issuedAt']!,
            expiresAt: testCase['expiresAt']!,
          ),
        ),
        throwsA(
          isA<RuntimePackageValidationException>().having(
            (error) => error.invalidKeys,
            'invalidKeys',
            contains(testCase['invalid']),
          ),
        ),
      );
    }
  });

  test('schema、target 与 profile trust domain 不一致时拒绝', () async {
    final schemaMismatch = await _signedPackage();
    // schema 是 package 的唯一身份键，没有并行的版本信封字段可判。
    (schemaMismatch['package']! as Map<String, Object?>)['schema'] =
        'app-runtime-config-package-other';
    await expectLater(
      _resolve(schemaMismatch),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          contains('schema'),
        ),
      ),
    );

    await expectLater(
      _resolve(await _signedPackage(target: 'alpha-local')),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          containsAll(<String>['target', 'environment']),
        ),
      ),
    );

    await expectLater(
      _resolve(
        await _signedPackage(
          environment: 'prod',
          buildProfile: 'nonprod',
          target: 'prod-hosted',
          deriveLaunchPolicy: true,
          runtime: _runtimeValues('prod'),
        ),
      ),
      throwsA(
        isA<RuntimePackageValidationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          containsAll(<String>['environment', 'buildProfile']),
        ),
      ),
    );
  });

  test('gray、channel、内容 release 与 secret 键只暴露键名后拒绝', () async {
    for (final forbiddenKey in <String>[
      'grayStage',
      'channel',
      'contentReleaseId',
      'apiSecret',
    ]) {
      final runtime = <String, String>{
        ..._runtimeValues('gamma'),
        forbiddenKey: 'do-not-expose-this-value',
      };
      await expectLater(
        _resolve(await _signedPackage(runtime: runtime)),
        throwsA(
          isA<RuntimePackageValidationException>()
              .having(
                (error) => error.invalidKeys,
                'invalidKeys',
                contains(forbiddenKey),
              )
              .having(
                (error) => error.toString(),
                'redacted',
                isNot(contains('do-not-expose-this-value')),
              ),
        ),
      );
    }
  });

  test('宿主 trust envelope 只接受精确字段且 keyring 必须是严格 Ed25519 公钥', () async {
    final extraFieldEnvelope = await _signedPackage();
    extraFieldEnvelope['unexpectedTrust'] = 'forbidden';
    await expectLater(
      CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
        bridge: NativeRuntimeConfigBridge(
          client: _EnvelopeClient(extraFieldEnvelope),
          maxAttempts: 1,
        ),
        resolver: _resolver(),
      ),
      throwsA(
        isA<CloudRuntimeConfigurationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['unexpectedTrust']),
        ),
      ),
    );

    final malformedKeyEnvelope = await _signedPackage();
    malformedKeyEnvelope['trustedPublicKeys'] = const <String, String>{
      'nonprod-2026-01': 'not-base64',
    };
    await expectLater(
      CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
        bridge: NativeRuntimeConfigBridge(
          client: _EnvelopeClient(malformedKeyEnvelope),
          maxAttempts: 1,
        ),
        resolver: _resolver(),
      ),
      throwsA(
        isA<CloudRuntimeConfigurationException>().having(
          (error) => error.invalidKeys,
          'invalidKeys',
          equals(<String>['trustedPublicKeys']),
        ),
      ),
    );
  });

  test('runtime package 未水合或非法时业务请求得到 typed unavailable', () {
    // 判读规则的输入就是脱敏摘要，因此这里直接喂非 complete 态，不靠测试之间的
    // 全局水合副作用制造。摘要自身的产出由上面的 resolver 用例把关。
    for (final state in <String>['missing', 'invalid']) {
      final failure = CloudRuntimeConfig.runtimeAvailabilityFailure(
        summary: <String, String>{
          'configurationSource': 'signed-runtime-package',
          'configurationState': state,
        },
      );
      expect(failure, isNotNull);
      expect(failure!.kind, RuntimeFailureKind.unavailable);
      expect(
        failure.code,
        OpsEventRecordErrorCode.startupConfigurationInvalid.code,
      );
      expect(failure.recovery.action, 'retry');
      expect(
        failure.context.attributes.any(
          (attribute) =>
              attribute.key == 'configurationState' && attribute.value == state,
        ),
        isTrue,
      );
      // 不可用判读绝不回传 URL，只回传脱敏的来源与状态。
      expect(
        failure.context.attributes.map((attribute) => attribute.value),
        everyElement(isNot(contains('://'))),
      );
    }
  });

  test('CloudRuntimeConfig 水合 Web 暴露的 package JSON 后读取外置 runtime values', () async {
    final trustEnvelope = await _signedPackage();
    final runtimePackage = Map<String, Object?>.from(
      trustEnvelope['package']! as Map,
    );
    await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
      bridge: NativeRuntimeConfigBridge(
        client: _EnvelopeClient(runtimePackage),
        maxAttempts: 1,
      ),
      resolver: _resolver(),
    );

    expect(runtimePackage, isNot(contains('package')));
    expect(runtimePackage, isNot(contains('trustedBuildProfile')));
    expect(runtimePackage, isNot(contains('trustedTarget')));
    expect(CloudRuntimeConfig.appRuntimeEnv, 'gamma');
    expect(CloudRuntimeConfig.gatewayBaseUrl, 'https://api.example.test');
    expect(
      CloudRuntimeConfig.graphqlEndpoint,
      'https://api.example.test/graphql',
    );
    expect(CloudRuntimeConfig.runtimeAvailabilityFailure(), isNull);
    expect(
      CloudRuntimeConfig.runtimeAvailabilityFailure(
        summary: (await _resolve(await _signedPackage())).runtimeDefineSummary,
      ),
      isNull,
    );
    expect(CloudRuntimeConfig.effectiveLaunchManifestDigest, isNull);
    expect(CloudRuntimeConfig.runtimeConfigTrustEnvelopeDigest, isNull);
    expect(
      CloudRuntimeConfig.runtimeConfigPackageDigest,
      'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(runtimePackage)))}',
    );
  });

  test('移动端 manifest digest 只读取原生 verified receipt identity', () async {
    final trustEnvelope = await _signedPackage();
    await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
      bridge: NativeRuntimeConfigBridge(
        client: _EnvelopeClient(trustEnvelope),
        maxAttempts: 1,
      ),
      resolver: _resolver(),
    );

    expect(
      CloudRuntimeConfig.effectiveLaunchManifestDigest,
      'sha256:${'c' * 64}',
    );
    expect(
      CloudRuntimeConfig.effectiveLaunchManifestDigest,
      isNot((trustEnvelope['package']! as Map)['sourceTreeDigest']),
    );
    expect(
      CloudRuntimeConfig.runtimeConfigPackageDigest,
      trustEnvelope['runtimeConfigPackageDigest'],
    );
    expect(
      CloudRuntimeConfig.runtimeConfigTrustEnvelopeDigest,
      trustEnvelope['runtimeConfigTrustEnvelopeDigest'],
    );
  });

  test('移动端 verified package/trust digest 漂移时 fail closed', () async {
    for (final field in <String>[
      'runtimeConfigPackageDigest',
      'runtimeConfigTrustEnvelopeDigest',
      'effectiveLaunchManifestDigest',
    ]) {
      final trustEnvelope = await _signedPackage();
      trustEnvelope[field] = field == 'effectiveLaunchManifestDigest'
          ? 'not-a-digest'
          : 'sha256:${'f' * 64}';

      await expectLater(
        CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
          bridge: NativeRuntimeConfigBridge(
            client: _EnvelopeClient(trustEnvelope),
            maxAttempts: 1,
          ),
          resolver: _resolver(),
        ),
        throwsA(
          isA<CloudRuntimeConfigurationException>()
              .having(
                (error) => error.reason,
                'reason',
                'runtime-verified-identity-invalid',
              )
              .having(
                (error) => error.invalidKeys,
                'invalidKeys',
                contains(field),
              ),
        ),
      );
    }
  });
}
