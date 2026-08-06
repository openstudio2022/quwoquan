import 'dart:io';

import 'package:quwoquan_app/cloud/runtime/errors/cloud_transport_failure.dart';

CloudTransportFailure? classifyCloudTransportFailure(Object error) {
  if (error is TlsException) {
    return const CloudTransportFailure(
      reason: CloudTransportFailureReason.secureConnection,
    );
  }
  if (error is! SocketException) {
    return null;
  }
  final platformErrorCode = error.osError?.errorCode;
  final reason = switch (platformErrorCode) {
    // Darwin/Linux/Windows connection refused.
    61 || 111 || 10061 => CloudTransportFailureReason.connectionRefused,
    // Darwin/Linux getaddrinfo EAI_NONAME/EAI_AGAIN.
    -3 ||
    -2 ||
    8 when error.address == null => CloudTransportFailureReason.nameResolution,
    // Darwin/Linux ENETDOWN and ENETUNREACH.
    50 || 51 || 100 || 101 => CloudTransportFailureReason.offline,
    _ => CloudTransportFailureReason.connectionFailed,
  };
  return CloudTransportFailure(
    reason: reason,
    platformErrorCode: platformErrorCode,
  );
}
