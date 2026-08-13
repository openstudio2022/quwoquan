import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

const _environmentName = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _gatewayBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

/// Canonical, fail-closed environment input for App API integration tests.
final class ApiContractEnvironment {
  const ApiContractEnvironment._();

  static CloudRuntimeEnvironment resolve() {
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
