import 'package:quwoquan_app/runtime/shell/recovery/recovery_runtime_binding.dart';

final class RecoveryVersionRequest {
  const RecoveryVersionRequest({
    required this.platform,
    required this.appVersion,
    required this.buildNumber,
  });

  final String platform;
  final String appVersion;
  final int buildNumber;
}

enum RecoveryUpdateState { none, available, required }

enum RecoveryVersionPlatform {
  android('android'),
  ios('ios'),
  web('web');

  const RecoveryVersionPlatform(this.wireName);

  final String wireName;
}

enum RecoveryVersionChannel { nativeUpdate, webOnly }

bool hasCanonicalRecoveryVersionTarget({
  required RecoveryVersionPlatform platform,
  required RecoveryVersionChannel channel,
  required String? updateUrl,
}) {
  final normalizedUpdateUrl = updateUrl?.trim();
  return switch (platform) {
    RecoveryVersionPlatform.ios =>
      channel == RecoveryVersionChannel.webOnly && normalizedUpdateUrl == null,
    RecoveryVersionPlatform.android || RecoveryVersionPlatform.web =>
      channel == RecoveryVersionChannel.nativeUpdate &&
          normalizedUpdateUrl != null &&
          normalizedUpdateUrl.isNotEmpty,
  };
}

final class RecoveryVersionResponse {
  const RecoveryVersionResponse({
    required this.platform,
    required this.latestVersion,
    required this.latestBuild,
    required this.minimumSupportedVersion,
    required this.minimumSupportedBuild,
    required this.updateState,
    required this.updateChannel,
    required this.updateUrl,
    required this.recoveryUrl,
  });

  final RecoveryVersionPlatform platform;
  final String latestVersion;
  final int latestBuild;
  final String minimumSupportedVersion;
  final int minimumSupportedBuild;
  final RecoveryUpdateState updateState;
  final RecoveryVersionChannel updateChannel;
  final String? updateUrl;
  final String recoveryUrl;
}

final class RecoveryFailurePayload {
  const RecoveryFailurePayload({
    required this.occurredAt,
    required this.appVersion,
    required this.buildNumber,
    required this.platform,
    required this.osVersion,
    required this.deviceModel,
    required this.errorSource,
    required this.errorType,
    required this.errorMessage,
    required this.stackTrace,
  });

  final DateTime occurredAt;
  final String appVersion;
  final String buildNumber;
  final String platform;
  final String osVersion;
  final String deviceModel;
  final String errorSource;
  final String errorType;
  final String errorMessage;
  final String stackTrace;
}

/// Shell 可见的启动恢复 typed facade；不暴露 generated client 或 HTTP。
abstract interface class RecoveryRuntimeOperations {
  Future<RecoveryVersionResponse> getVersion(RecoveryVersionRequest request);

  Future<void> reportFailure(RecoveryFailurePayload payload);
}

typedef RecoveryRuntimeOperationsFactory = RecoveryRuntimeOperations Function(
  RecoveryRuntimeBinding binding,
);

/// 由 runtime/di 在普通 runtime config hydration 前安装 production factory。
final class RecoveryRuntimeOperationsRegistry {
  RecoveryRuntimeOperationsRegistry._();

  static final RecoveryRuntimeOperationsRegistry instance =
      RecoveryRuntimeOperationsRegistry._();

  RecoveryRuntimeOperationsFactory? _factory;
  String? _activeBindingIdentity;
  RecoveryRuntimeOperations? _activeOperations;

  bool get isConfigured => _factory != null;

  void configure(RecoveryRuntimeOperationsFactory factory) {
    if (_activeOperations != null) {
      throw StateError('recovery runtime operations are already active');
    }
    _factory = factory;
  }

  RecoveryRuntimeOperations resolve(RecoveryRuntimeBinding binding) {
    final factory = _factory;
    if (factory == null) {
      throw StateError('recovery runtime operations are not configured');
    }
    final activeIdentity = _activeBindingIdentity;
    if (activeIdentity != null && activeIdentity != binding.identity) {
      throw StateError('recovery runtime binding changed during one bootstrap');
    }
    _activeBindingIdentity = binding.identity;
    return _activeOperations ??= factory(binding);
  }
}

final class RecoveryOperationGateway {
  RecoveryOperationGateway({this.operations});

  final RecoveryRuntimeOperations? operations;

  RecoveryRuntimeOperations _resolve(RecoveryRuntimeBinding binding) =>
      operations ?? RecoveryRuntimeOperationsRegistry.instance.resolve(binding);

  Future<RecoveryVersionResponse> getAppRecoveryVersion({
    required RecoveryRuntimeBinding binding,
    required String platform,
    required String appVersion,
    required int buildNumber,
  }) {
    return _resolve(binding).getVersion(
      RecoveryVersionRequest(
        platform: platform,
        appVersion: appVersion,
        buildNumber: buildNumber,
      ),
    );
  }

  Future<void> reportRecoveryFailure({
    required RecoveryRuntimeBinding binding,
    required RecoveryFailurePayload request,
  }) => _resolve(binding).reportFailure(request);
}
