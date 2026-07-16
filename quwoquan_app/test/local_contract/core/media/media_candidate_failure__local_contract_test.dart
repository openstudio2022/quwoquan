import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_candidate_failure.dart';

void main() {
  group('classifyMediaCandidateLoadFailure', () {
    test('classifies canonical env.test DNS failures', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'ClientException with SocketException: Failed host lookup: '
            "'alpha-image.quwoquan-env.test'",
          ),
          candidateUrl:
              'https://alpha-image.quwoquan-env.test:17100/media/image/s/x.png',
        ),
        MediaCandidateFailureKind.dnsNxdomain,
      );
    });

    test('classifies certificate verify failures on loopback', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('HandshakeException: CERTIFICATE_VERIFY_FAILED'),
          candidateUrl: 'https://localhost:17100/media/image/s/x.png',
        ),
        MediaCandidateFailureKind.certificateVerifyFailed,
      );
    });

    test('classifies handshake terminated separately from cert verify', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'HandshakeException: Connection terminated during handshake',
          ),
          candidateUrl: 'https://127.0.0.1:17100/media/image/s/x.png',
        ),
        MediaCandidateFailureKind.handshakeTerminated,
      );
    });

    test('classifies connection refused on adb reverse path', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('SocketException: Connection refused'),
          candidateUrl: 'https://127.0.0.1:17100/media/image/s/x.png',
        ),
        MediaCandidateFailureKind.connectionRefused,
      );
    });
  });
}
