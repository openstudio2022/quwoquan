import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// Installs the repo-managed local HTTPS CA for Dart's networking stack.
///
/// 平台系统信任库与 `dart:io` [HttpClient] 的信任库并不总是同源。加载由
/// 本地 target 构建步骤注入的 Debug/Profile CA 到 [SecurityContext.defaultContext]
/// 后，iOS Simulator 与 Android 均可使用同一条本地 HTTPS 连接，不需要关闭
/// 证书校验或回退 HTTP。
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
  static bool _loopbackResolverInstalled = false;

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
      isIos: Platform.isIOS,
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
        'Local HTTPS trust root is required for local HTTPS bases, '
        'but the Debug/Profile bundle did not expose local_env_debug_root.',
      );
    }
    if (isPlaceholderLocalEnvCertificate(certBytes)) {
      throw StateError(
        'Local HTTPS trust root is the debug placeholder CA; refuse to install '
        'it. Launch via stackctl so the canonical target CA is exported.',
      );
    }
    SecurityContext.defaultContext.setTrustedCertificatesBytes(certBytes);
    _installLocalLoopbackResolver();
    _installed = true;
  }

  static void _installLocalLoopbackResolver() {
    if (_loopbackResolverInstalled) {
      return;
    }
    // iOS Simulator 会优先把 `*.localhost` 解析为 ::1；而 Colima 的本地
    // target 端口只发布在 127.0.0.1。保留原始 host 作为 TLS SNI 与证书校验名，
    // 仅将本地 Debug/Profile 连接的 TCP peer 固定到 IPv4 loopback。
    HttpOverrides.global = _LocalLoopbackHttpOverrides();
    _loopbackResolverInstalled = true;
  }

  @visibleForTesting
  static bool shouldInstallForRuntime({
    required bool isReleaseMode,
    required bool isAndroid,
    bool isIos = false,
    required Iterable<String> runtimeBases,
    @Deprecated('Ignored; install is plane-based, not env-name-based')
    String? appRuntimeEnv,
  }) {
    if (isReleaseMode || (!isAndroid && !isIos)) {
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

final class _LocalLoopbackHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(
      context ?? SecurityContext.defaultContext,
    );
    client.findProxy = (_) => 'DIRECT';
    client.connectionFactory = (uri, proxyHost, proxyPort) {
      final secure = uri.scheme == 'https';
      final socketTask = Socket.startConnect(
        LocalDevHttpsTrust.isLocalHttpsTransportBase(uri.toString())
            ? InternetAddress.loopbackIPv4.address
            : uri.host,
        uri.port,
      );
      return socketTask.then((task) {
        if (!secure) {
          return task;
        }
        final secureSocket = task.socket.then<Socket>(
          (socket) => SecureSocket.secure(
            socket,
            host: uri.host,
            context: context ?? SecurityContext.defaultContext,
          ),
        );
        return ConnectionTask.fromSocket<Socket>(secureSocket, task.cancel);
      });
    };
    return client;
  }
}
