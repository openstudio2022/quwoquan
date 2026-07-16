import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// Installs the repo-managed local HTTPS CA for Dart's networking stack.
///
/// Android `network_security_config` is honored by the platform networking
/// stack, while `cached_network_image` and `flutter_cache_manager` use
/// `dart:io` [HttpClient]. Loading the same debug/profile CA into
/// [SecurityContext.defaultContext] keeps local Android HTTPS media working
/// without certificate-validation bypasses or HTTP fallback paths.
///
/// Install decisions are based on **injected runtime bases** (host plane) and
/// release mode — never on `APP_RUNTIME_ENV` name strings — so prod-sim
/// (`*.localhost` bases) installs while prod-hosted (public IP) stays no-op.
class LocalDevHttpsTrust {
  LocalDevHttpsTrust._();

  static const MethodChannel _channel = MethodChannel(
    'quwoquan/runtime/local_dev_https_trust',
  );

  /// ASCII subject CN of the Gradle placeholder cert; must never be treated as
  /// a successful local trust root.
  static const String placeholderSubjectMarker =
      'quwoquan-local-debug-placeholder';

  static bool _installed = false;

  /// Whether [installForCurrentRuntime] successfully loaded a real CA.
  static bool get isInstalled => _installed;

  @visibleForTesting
  static void resetInstalledForTest() {
    _installed = false;
  }

  static Future<void> installForCurrentRuntime() async {
    if (_installed) {
      return;
    }
    final shouldInstall = shouldInstallForRuntime(
      isReleaseMode: kReleaseMode,
      isAndroid: Platform.isAndroid,
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
        'Android local HTTPS trust root is required for local HTTPS bases, '
        'but the APK did not expose local_env_debug_root.',
      );
    }
    if (isPlaceholderLocalEnvCertificate(certBytes)) {
      throw StateError(
        'Android local HTTPS trust root is the debug placeholder CA; refuse '
        'to install it. Launch via make dev-up / stackctl with a real exported '
        'CA, or set QWQ_ANDROID_LOCAL_ENV_CA_PATH.',
      );
    }
    SecurityContext.defaultContext.setTrustedCertificatesBytes(certBytes);
    _installed = true;
  }

  @visibleForTesting
  static bool shouldInstallForRuntime({
    required bool isReleaseMode,
    required bool isAndroid,
    required Iterable<String> runtimeBases,
    @Deprecated('Ignored; install is plane-based, not env-name-based')
    String? appRuntimeEnv,
  }) {
    if (isReleaseMode || !isAndroid) {
      return false;
    }
    return runtimeBases.any(isLocalHttpsTransportBase);
  }

  /// True when [raw] is an HTTPS URL whose host is on the local device plane
  /// (`localhost` / loopback / `*.localhost`). Canonical `*.quwoquan-env.test`
  /// alone does **not** trigger install — that plane is for Mac/iOS hosts DNS.
  @visibleForTesting
  static bool isLocalHttpsTransportBase(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      return false;
    }
    final host = uri.host.toLowerCase();
    return host == 'localhost' ||
        host == '127.0.0.1' ||
        host == '::1' ||
        host == '10.0.2.2' ||
        host.endsWith('.localhost');
  }

  @visibleForTesting
  static bool isPlaceholderLocalEnvCertificate(Uint8List certBytes) {
    final asLatin1 = latin1.decode(certBytes, allowInvalid: true);
    if (asLatin1.contains(placeholderSubjectMarker)) {
      return true;
    }
    // DER often embeds the CN as UTF-8 / printable ASCII without PEM wrapping.
    final markerBytes = utf8.encode(placeholderSubjectMarker);
    if (markerBytes.isEmpty || certBytes.length < markerBytes.length) {
      return false;
    }
    outer:
    for (var i = 0; i <= certBytes.length - markerBytes.length; i++) {
      for (var j = 0; j < markerBytes.length; j++) {
        if (certBytes[i + j] != markerBytes[j]) {
          continue outer;
        }
      }
      return true;
    }
    return false;
  }
}
