import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

enum CloudEnvironment { alpha, beta, gamma, prod }

final class CloudRuntimeEnvironment {
  CloudRuntimeEnvironment({
    required this.environment,
    required Uri gatewayBaseUri,
  }) : _gatewayBaseUri = gatewayBaseUri {
    if (!gatewayBaseUri.hasScheme || gatewayBaseUri.host.isEmpty) {
      throw ArgumentError.value(
        gatewayBaseUri,
        'gatewayBaseUri',
        'Gateway base URI must be absolute',
      );
    }
    if (gatewayBaseUri.userInfo.isNotEmpty ||
        gatewayBaseUri.hasQuery ||
        gatewayBaseUri.hasFragment) {
      throw ArgumentError.value(
        gatewayBaseUri,
        'gatewayBaseUri',
        'Gateway base URI cannot contain credentials, query, or fragment',
      );
    }
    if (environment == CloudEnvironment.prod &&
        gatewayBaseUri.scheme != 'https') {
      throw ArgumentError.value(
        gatewayBaseUri,
        'gatewayBaseUri',
        'Production Gateway must use HTTPS',
      );
    }
  }

  CloudRuntimeEnvironment.offline({required this.environment})
    : _gatewayBaseUri = null {
    if (environment != CloudEnvironment.alpha) {
      throw CloudRuntimeConfigurationException(
        reason: 'runtime_config_content_source_mismatch',
      );
    }
  }

  final CloudEnvironment environment;
  final Uri? _gatewayBaseUri;

  Uri? get gatewayBaseUriOrNull => _gatewayBaseUri;
  bool get networkAccessAllowed => _gatewayBaseUri != null;
  Uri get gatewayBaseUri =>
      _gatewayBaseUri ??
      (throw CloudRuntimeConfigurationException(
        reason: 'runtime_config_network_forbidden',
        source: 'signed-offline-bootstrap',
        runtimeEnv: environment.name,
        invalidKeys: const ['gatewayBaseUrl'],
      ));

  factory CloudRuntimeEnvironment.fromCompileTime() {
    final environmentValue = CloudRuntimeConfig.appRuntimeEnv;
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == environmentValue,
      orElse: () =>
          throw StateError('Unsupported APP_RUNTIME_ENV: $environmentValue'),
    );
    if (!CloudRuntimeConfig.networkAccessAllowed) {
      return CloudRuntimeEnvironment.offline(environment: environment);
    }
    return CloudRuntimeEnvironment(
      environment: environment,
      gatewayBaseUri: Uri.parse(CloudRuntimeConfig.gatewayBaseUrl),
    );
  }
}
