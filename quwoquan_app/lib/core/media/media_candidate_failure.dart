/// Classifies media candidate load failures for local env diagnostics.
///
/// Distinguishes loopback TLS/tunnel failures from canonical DNS misses so
/// operators fix CA / adb reverse instead of deleting topology hostnames.
enum MediaCandidateFailureKind {
  /// `Failed host lookup` / NXDOMAIN for `*.quwoquan-env.test`.
  dnsNxdomain,

  /// TLS handshake aborted before certificate verification completed.
  handshakeTerminated,

  /// Peer certificate failed verification (often missing local CA in Dart).
  certificateVerifyFailed,

  /// Connection refused / reset on localhost (adb reverse / edge down).
  connectionRefused,

  /// Other / unclassified.
  other,
}

MediaCandidateFailureKind classifyMediaCandidateLoadFailure(
  Object error, {
  String? candidateUrl,
}) {
  final text = error.toString().toLowerCase();
  final host = Uri.tryParse(candidateUrl ?? '')?.host.toLowerCase() ?? '';
  final looksLikeEnvTest =
      host.endsWith('.quwoquan-env.test') || text.contains('.quwoquan-env.test');

  if (text.contains('failed host lookup') ||
      text.contains('no address associated with hostname') ||
      text.contains('name or service not known') ||
      text.contains('nodename nor servname')) {
    if (looksLikeEnvTest) {
      return MediaCandidateFailureKind.dnsNxdomain;
    }
    return MediaCandidateFailureKind.other;
  }

  if (text.contains('certificate_verify_failed') ||
      text.contains('certificateverifyfailed') ||
      text.contains('certificate verify failed') ||
      (text.contains('certificate') && text.contains('verify'))) {
    return MediaCandidateFailureKind.certificateVerifyFailed;
  }

  if (text.contains('handshake') ||
      text.contains('connection terminated during handshake') ||
      text.contains('ssl') ||
      text.contains('tls')) {
    return MediaCandidateFailureKind.handshakeTerminated;
  }

  if (text.contains('connection refused') ||
      text.contains('connection reset') ||
      text.contains('network is unreachable') ||
      text.contains('software caused connection abort')) {
    return MediaCandidateFailureKind.connectionRefused;
  }

  return MediaCandidateFailureKind.other;
}
