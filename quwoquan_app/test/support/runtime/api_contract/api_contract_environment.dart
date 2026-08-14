import 'dart:io' show SecurityContext;

import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

const _environmentName = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _gatewayBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

/// *-local 环境的网关证书由 target 私有根签发；根证书路径是 canonical 启动器
/// 注入的环境输入之一。信任建立收敛在本 resolver 单点，harness 一律不得
/// 自行触碰 dart:io——TLS 校验永不关闭，空值时保持 Dart 内置信任链不变。
const _localTlsRootFile = String.fromEnvironment('QWQ_LOCAL_TLS_ROOT_FILE');
var _localTlsRootInstalled = false;

/// Canonical, fail-closed environment input for App API integration tests.
final class ApiContractEnvironment {
  const ApiContractEnvironment._();

  static void ensureLocalTlsRootTrusted() {
    if (_localTlsRootFile.isEmpty || _localTlsRootInstalled) {
      return;
    }
    SecurityContext.defaultContext.setTrustedCertificates(_localTlsRootFile);
    _localTlsRootInstalled = true;
  }

  static CloudRuntimeEnvironment resolve() {
    ensureLocalTlsRootTrusted();
    if (_gatewayBase.trim().isEmpty) {
      throw StateError(
        'L3: API_CONTRACT_BASE_URL was not injected by the canonical '
        'stackctl App API integration launcher',
      );
    }
    final gatewayBaseUri = Uri.tryParse(_gatewayBase.trim());
    if (gatewayBaseUri == null ||
        !gatewayBaseUri.isAbsolute ||
        gatewayBaseUri.scheme != 'https' ||
        gatewayBaseUri.host.isEmpty ||
        gatewayBaseUri.userInfo.isNotEmpty ||
        gatewayBaseUri.hasFragment ||
        gatewayBaseUri.hasQuery) {
      throw StateError(
        'L3: API_CONTRACT_BASE_URL must be an absolute first-party HTTPS base',
      );
    }
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == _environmentName,
      orElse: () =>
          throw StateError('Unsupported API_CONTRACT_ENV: $_environmentName'),
    );
    return CloudRuntimeEnvironment(
      environment: environment,
      gatewayBaseUri: gatewayBaseUri,
    );
  }
}
