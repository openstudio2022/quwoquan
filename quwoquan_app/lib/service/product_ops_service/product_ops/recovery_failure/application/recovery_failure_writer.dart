final class RecoveryFailureRecord {
  const RecoveryFailureRecord({
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

abstract interface class RecoveryFailureWriter {
  Future<void> write(RecoveryFailureRecord record);
}
