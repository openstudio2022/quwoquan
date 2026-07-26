import 'dart:convert';
import 'dart:typed_data';

class LocalDevHttpsTrust {
  LocalDevHttpsTrust._();

  static bool get isInstalled => false;

  static Future<void> installForCurrentRuntime() async {}

  static bool shouldInstallForRuntime({
    required bool isReleaseMode,
    required bool isAndroid,
    bool isIos = false,
    required Iterable<String> runtimeBases,
    String? appRuntimeEnv,
  }) {
    return false;
  }

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

  static bool shouldResolveThroughLocalLoopback(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      return false;
    }
    return isLocalHttpsTransportBase(raw) ||
        uri.host.toLowerCase().endsWith('.quwoquan-env.test');
  }

  static bool isPlaceholderLocalEnvCertificate(Uint8List certBytes) {
    const marker = 'quwoquan-local-debug-placeholder';
    return latin1.decode(certBytes, allowInvalid: true).contains(marker);
  }
}
