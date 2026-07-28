enum CloudTransportFailureReason {
  secureConnection,
  connectionRefused,
  nameResolution,
  offline,
  connectionFailed,
}

final class CloudTransportFailure {
  const CloudTransportFailure({required this.reason, this.platformErrorCode});

  final CloudTransportFailureReason reason;
  final int? platformErrorCode;
}

typedef CloudTransportFailureClassifier =
    CloudTransportFailure? Function(Object error);
