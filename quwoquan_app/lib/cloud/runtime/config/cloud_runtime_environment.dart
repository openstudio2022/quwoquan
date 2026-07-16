enum CloudEnvironment { alpha, beta, gamma, prod }

final class CloudRuntimeEnvironment {
  CloudRuntimeEnvironment({
    required this.environment,
    required this.gatewayBaseUri,
  }) {
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

  final CloudEnvironment environment;
  final Uri gatewayBaseUri;

  factory CloudRuntimeEnvironment.fromCompileTime() {
    const environmentValue = String.fromEnvironment(
      'APP_RUNTIME_ENV',
      defaultValue: 'alpha',
    );
    const gatewayValue = String.fromEnvironment(
      'CLOUD_GATEWAY_BASE_URL',
      defaultValue: 'https://alpha-api.quwoquan-env.test:17000',
    );
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == environmentValue,
      orElse: () =>
          throw StateError('Unsupported APP_RUNTIME_ENV: $environmentValue'),
    );
    return CloudRuntimeEnvironment(
      environment: environment,
      gatewayBaseUri: Uri.parse(gatewayValue),
    );
  }
}
