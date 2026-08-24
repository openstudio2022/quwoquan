/// 宿主测试树的唯一 runtime package 水合入口。
///
/// 生产装配把 runtime 配置从编译期 `--dart-define` 迁到冷启动原生 signed
/// package 之后，`CloudRuntimeConfig` 的读取面只承认「已水合的 package」。
/// 宿主测试没有原生 activation 事务，因此必须在测试树内用 typed double 走完
/// 同一条 resolver 校验链：真实 Ed25519 签名、真实 canonical digest、真实
/// trust envelope 字段集。这里刻意不提供任何绕过 resolver 的旁路，否则
/// 宿主测试会验证一条生产上不存在的读取路径。
library;

import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:cryptography/cryptography.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';

/// 受管测试 runner 注入的运行时取值；键与 `RUNTIME_VALUE_DEFINE_KEYS` 同源。
///
/// 缺省值只在缺 define 时兜底，保证纯 `flutter test` 也能得到结构合法的
/// package；真实取值仍由 runner 从环境拓扑注入，宿主测试因此看到与
/// canonical launcher 相同的 endpoint 形状。
const _appRuntimeEnv = String.fromEnvironment(
  'APP_RUNTIME_ENV',
  defaultValue: 'gamma',
);
const _gatewayBaseUrl = String.fromEnvironment(
  'CLOUD_GATEWAY_BASE_URL',
  defaultValue: 'https://api.example.test',
);
const _legalBaseUrl = String.fromEnvironment(
  'APP_LEGAL_BASE_URL',
  defaultValue: 'https://www.example.test/legal',
);
const _publicWebBaseUrl = String.fromEnvironment(
  'PUBLIC_WEB_BASE_URL',
  defaultValue: 'https://www.example.test',
);
const _mediaAvatarCdnBaseUrl = String.fromEnvironment(
  'MEDIA_AVATAR_CDN_BASE_URL',
  defaultValue: 'https://cdn.example.test/media/avatar',
);
const _mediaImageCdnBaseUrl = String.fromEnvironment(
  'MEDIA_IMAGE_CDN_BASE_URL',
  defaultValue: 'https://cdn.example.test/media/image',
);
const _mediaVideoCdnBaseUrl = String.fromEnvironment(
  'MEDIA_VIDEO_CDN_BASE_URL',
  defaultValue: 'https://cdn.example.test/media/video',
);
const _mediaUploadBaseUrl = String.fromEnvironment(
  'MEDIA_UPLOAD_BASE_URL',
  defaultValue: 'https://upload.example.test',
);
const _rtcMediaConnectionUrl = String.fromEnvironment(
  'RTC_MEDIA_CONNECTION_URL',
  defaultValue: 'wss://rtc.example.test',
);

const _issuedAt = '2026-08-22T11:55:00Z';
const _expiresAt = '2026-08-22T13:00:00Z';
const _validAt = '2026-08-22T12:00:00Z';

/// realtime endpoint 由 gateway authority 派生，避免与网关分叉成第二真相源。
/// `Uri.origin` 只支持 http/https，因此这里显式拼 scheme 与 authority。
String _realtimeBaseUrl() {
  final gateway = Uri.parse(_gatewayBaseUrl);
  final scheme = gateway.isScheme('http') ? 'ws' : 'wss';
  return '$scheme://${gateway.authority}';
}

/// download endpoint 同样锚定在 public web authority 上。
String _appDownloadBaseUrl() => '$_publicWebBaseUrl/download';

Map<String, String> _runtimeValues() => <String, String>{
  'appRuntimeEnv': _appRuntimeEnv,
  'gatewayBaseUrl': _gatewayBaseUrl,
  'legalBaseUrl': _legalBaseUrl,
  'publicWebBaseUrl': _publicWebBaseUrl,
  'appDownloadBaseUrl': _appDownloadBaseUrl(),
  'realtimeBaseUrl': _realtimeBaseUrl(),
  'mediaAvatarCdnBaseUrl': _mediaAvatarCdnBaseUrl,
  'mediaImageCdnBaseUrl': _mediaImageCdnBaseUrl,
  'mediaVideoCdnBaseUrl': _mediaVideoCdnBaseUrl,
  'mediaUploadBaseUrl': _mediaUploadBaseUrl,
  'rtcMediaConnectionUrl': _rtcMediaConnectionUrl,
};

final class _HydrationChannelClient implements RuntimeConfigChannelClient {
  const _HydrationChannelClient(this.envelope);

  final Map<String, Object?> envelope;

  @override
  Future<Object?> invokeMethod(String method) async => envelope;
}

/// 用宿主内生成的密钥对签出一份 trust envelope，字段集与原生 activation
/// 交出的 envelope 完全一致。
Future<Map<String, Object?>> buildSignedTrustEnvelopeForTests({
  String buildProfile = 'nonprod',
  String? target,
}) async {
  final resolvedTarget = target ?? '$_appRuntimeEnv-local';
  final algorithm = Ed25519();
  final keyPair = await algorithm.newKeyPair();
  final publicKey = await keyPair.extractPublicKey();
  final trustedPublicKeys = <String, String>{
    'nonprod-2026-01': base64.encode(publicKey.bytes),
  };
  final payload = <String, Object?>{
    'buildProfile': buildProfile,
    'environment': _appRuntimeEnv,
    'expiresAt': _expiresAt,
    'issuedAt': _issuedAt,
    'launchPolicy': runtimePackageTestLiveLaunchPolicy,
    'payloadDigest': '',
    'runtime': _runtimeValues(),
    'schema': runtimePackageSchema,
    'signatureAlgorithm': 'ed25519',
    'signatureKeyId': 'nonprod-2026-01',
    'sourceGitSha': 'a' * 40,
    'sourceTreeDigest': 'sha256:${'b' * 64}',
    'target': resolvedTarget,
    'trustedPublicKeys': trustedPublicKeys,
  };
  payload['payloadDigest'] =
      'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(payload)))}';
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
    'trustedTarget': resolvedTarget,
    'trustedPublicKeys': trustedPublicKeys,
    'runtimeConfigPackageDigest':
        'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(runtimePackage)))}',
    'runtimeConfigTrustEnvelopeDigest':
        'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(trustDocument)))}',
    'effectiveLaunchManifestDigest': 'sha256:${'c' * 64}',
  };
}

/// 让 `CloudRuntimeConfig` 进入已水合态。失败必须抛出，不允许静默降级——
/// 否则整棵测试树会退回到「未水合」并把回归伪装成断言失败。
Future<void> hydrateRuntimePackageForTests() async {
  final envelope = await buildSignedTrustEnvelopeForTests();
  await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
    bridge: NativeRuntimeConfigBridge(
      client: _HydrationChannelClient(envelope),
      maxAttempts: 1,
    ),
    resolver: RuntimePackageResolver(now: () => DateTime.parse(_validAt)),
  );
}
