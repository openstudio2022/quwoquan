/// Classifies native player and Dart media candidate failures without exposing
/// their raw transport text to consumers.
enum MediaCandidateFailureKind {
  /// The device explicitly reported that its network is unreachable.
  networkUnavailable,

  /// `Failed host lookup` / NXDOMAIN from a native or Dart network stack.
  dnsNxdomain,

  /// TLS handshake aborted before certificate verification completed.
  handshakeTerminated,

  /// Peer certificate failed verification (often missing local CA in Dart).
  certificateVerifyFailed,

  /// Connection refused / reset on localhost (adb reverse / edge down).
  connectionRefused,

  /// No cached or trusted network source can be handed to the native player.
  noPlayableSource,

  /// Timed out while waiting for a bounded native controller slot.
  controllerSlotTimeout,

  /// Native decoder rejected the media during controller initialization.
  decoderInitialization,

  /// HTTP 404 from CDN/edge (asset missing); terminal for negative cache.
  http404,

  /// Other HTTP 4xx (excluding 404).
  http4xx,

  /// HTTP 5xx from CDN/edge.
  http5xx,

  /// Other / unclassified.
  other,
}

/// Best-effort extraction of HTTP status from cache_manager / http errors.
int? extractHttpStatusCode(Object error) {
  final dynamic dynamicError = error;
  try {
    final statusCode = dynamicError.statusCode;
    if (statusCode is int) {
      return statusCode;
    }
  } catch (_) {
    // Not an HttpExceptionWithStatus-like object.
  }
  final match = RegExp(
    r'(?:status(?:\s*code)?|response\s*code|invalid\s*statuscode)'
    r'[:=\s]+(\d{3})',
    caseSensitive: false,
  ).firstMatch(error.toString());
  if (match == null) {
    return null;
  }
  return int.tryParse(match.group(1)!);
}

MediaCandidateFailureKind classifyMediaCandidateLoadFailure(
  Object error, {
  String? candidateUrl,
}) {
  final text = error.toString().toLowerCase();
  final nativeUrlErrorCode = RegExp(
    r'(?:nsurlerrordomain\s+error|error\s+domain\s*=\s*nsurlerrordomain'
    r'\s*,?\s*code)\s*(-?\d+)',
  ).firstMatch(text);
  final urlErrorCode = nativeUrlErrorCode == null
      ? null
      : int.tryParse(nativeUrlErrorCode.group(1)!);
  switch (urlErrorCode) {
    case -1200: // NSURLErrorSecureConnectionFailed
    case -1202: // NSURLErrorServerCertificateUntrusted
      return MediaCandidateFailureKind.certificateVerifyFailed;
    case -1003: // NSURLErrorCannotFindHost
      return MediaCandidateFailureKind.dnsNxdomain;
    case -1004: // NSURLErrorCannotConnectToHost
    case -1005: // NSURLErrorNetworkConnectionLost
    case -1001: // NSURLErrorTimedOut
      return MediaCandidateFailureKind.connectionRefused;
    case -1009: // NSURLErrorNotConnectedToInternet
      return MediaCandidateFailureKind.networkUnavailable;
  }
  final statusCode = extractHttpStatusCode(error);
  if (statusCode == 404) {
    return MediaCandidateFailureKind.http404;
  }
  if (statusCode != null && statusCode >= 400 && statusCode < 500) {
    return MediaCandidateFailureKind.http4xx;
  }
  if (statusCode != null && statusCode >= 500 && statusCode < 600) {
    return MediaCandidateFailureKind.http5xx;
  }
  if (text.contains('httpexceptionwithstatus') && text.contains('404')) {
    return MediaCandidateFailureKind.http404;
  }

  if (text.contains('unable to resolve host') ||
      text.contains('failed host lookup') ||
      text.contains('no address associated with hostname') ||
      text.contains('name or service not known') ||
      text.contains('nodename nor servname')) {
    return MediaCandidateFailureKind.dnsNxdomain;
  }

  if (text.contains('certificate_verify_failed') ||
      text.contains('certificateverifyfailed') ||
      text.contains('certificate verify failed') ||
      text.contains('sslpeerunverifiedexception') ||
      text.contains('certpathvalidatorexception') ||
      text.contains('trust anchor') ||
      (text.contains('certificate') && text.contains('verify'))) {
    return MediaCandidateFailureKind.certificateVerifyFailed;
  }

  if (text.contains('handshake') ||
      text.contains('connection terminated during handshake') ||
      text.contains('ssl') ||
      text.contains('tls')) {
    return MediaCandidateFailureKind.handshakeTerminated;
  }

  if (text.contains('network is unreachable')) {
    return MediaCandidateFailureKind.networkUnavailable;
  }

  if (text.contains('connection refused') ||
      text.contains('connection reset') ||
      text.contains('software caused connection abort')) {
    return MediaCandidateFailureKind.connectionRefused;
  }

  return MediaCandidateFailureKind.other;
}
