import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// Installs the repo-managed local HTTPS CA for Dart's networking stack.
///
/// Android `network_security_config` is honored by the platform networking
/// stack, while `cached_network_image` and `flutter_cache_manager` use
/// `dart:io` [HttpClient]. Loading the same debug/profile CA into
/// [SecurityContext.defaultContext] keeps alpha local media HTTPS-only without
/// certificate-validation bypasses or HTTP fallback paths.
class LocalDevHttpsTrust {
  LocalDevHttpsTrust._();

  static const MethodChannel _channel = MethodChannel(
    'quwoquan/runtime/local_dev_https_trust',
  );

  static bool _installed = false;

  static Future<void> installForCurrentRuntime() async {
    if (_installed) {
      return;
    }
    final shouldInstall = shouldInstallForRuntime(
      isReleaseMode: kReleaseMode,
      isAndroid: Platform.isAndroid,
      appRuntimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      runtimeBases: const <String>[
        CloudRuntimeConfig.gatewayBaseUrl,
        CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        CloudRuntimeConfig.mediaImageCdnBaseUrl,
        CloudRuntimeConfig.mediaVideoCdnBaseUrl,
        CloudRuntimeConfig.mediaUploadBaseUrl,
      ],
    );
    if (!shouldInstall) {
      return;
    }

    final certBytes = await _channel.invokeMethod<Uint8List>(
      'localEnvDebugRootCertificate',
    );
    if (certBytes == null || certBytes.isEmpty) {
      throw StateError(
        'Android local HTTPS trust root is required for local alpha media, '
        'but the APK did not expose local_env_debug_root.',
      );
    }
    SecurityContext.defaultContext.setTrustedCertificatesBytes(certBytes);
    _installed = true;
  }

  @visibleForTesting
  static bool shouldInstallForRuntime({
    required bool isReleaseMode,
    required bool isAndroid,
    required String appRuntimeEnv,
    required Iterable<String> runtimeBases,
  }) {
    if (isReleaseMode || !isAndroid || appRuntimeEnv == 'prod') {
      return false;
    }
    return runtimeBases.any(_isLocalDevHttpsBase);
  }

  static bool _isLocalDevHttpsBase(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      return false;
    }
    final host = uri.host.toLowerCase();
    return host == 'localhost' ||
        host == '127.0.0.1' ||
        host == '10.0.2.2' ||
        host.endsWith('.quwoquan-env.test') ||
        host.endsWith('.localhost');
  }
}
