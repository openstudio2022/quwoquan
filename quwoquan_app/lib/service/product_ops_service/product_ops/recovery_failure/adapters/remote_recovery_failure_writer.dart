import 'package:quwoquan_app/service/product_ops_service/product_ops/recovery_failure/application/recovery_failure_writer.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef RecoveryFailureInvocationContextFactory =
    CloudOperationInvocationContext Function();

final class RemoteRecoveryFailureWriter implements RecoveryFailureWriter {
  const RemoteRecoveryFailureWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RecoveryFailureInvocationContextFactory invocationContext;

  @override
  Future<void> write(RecoveryFailureRecord record) {
    return client.opsRecoveryFailureReportRecoveryFailure(
      ops_contracts.ReportRecoveryFailureRequest(
        occurredAt: record.occurredAt,
        appVersion: record.appVersion,
        buildNumber: record.buildNumber,
        platform: record.platform,
        osVersion: record.osVersion,
        deviceModel: record.deviceModel,
        errorSource: record.errorSource,
        errorType: record.errorType,
        errorMessage: record.errorMessage,
        stackTrace: record.stackTrace,
      ),
      context: invocationContext(),
    );
  }
}
