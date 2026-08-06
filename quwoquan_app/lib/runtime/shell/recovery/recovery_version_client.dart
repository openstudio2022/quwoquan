import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_runtime_binding.dart';

typedef RecoveryVersionResult = RecoveryVersionResponse;

final class RecoveryVersionClient {
  RecoveryVersionClient({RecoveryOperationGateway? gateway})
    : _gateway = gateway ?? RecoveryOperationGateway();

  final RecoveryOperationGateway _gateway;

  Future<RecoveryVersionResult> fetch({
    required RecoveryRuntimeBinding binding,
    required String platform,
    required String appVersion,
    required int buildNumber,
  }) async {
    final response = await _gateway.getAppRecoveryVersion(
      binding: binding,
      platform: platform,
      appVersion: appVersion,
      buildNumber: buildNumber,
    );
    final result = RecoveryVersionResult(
      latestVersion: response.latestVersion.trim(),
      latestBuild: response.latestBuild,
      updateUrl: response.updateUrl.trim(),
      recoveryUrl: response.recoveryUrl.trim(),
    );
    if (result.latestVersion.isEmpty || result.latestBuild <= 0) {
      throw const FormatException('invalid recovery release values');
    }
    return result;
  }
}
