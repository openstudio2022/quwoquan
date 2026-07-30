import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_candidate_failure.dart';

void main() {
  group('classifyMediaCandidateLoadFailure', () {
    test('classifies canonical env.test DNS failures', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'ClientException with SocketException: Failed host lookup: '
            "'cdn.alpha.quwoquan.com'",
          ),
          candidateUrl:
              'https://cdn.alpha.quwoquan.com:17100/media/image/s/x.png',
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

    test('classifies explicit network unreachable separately', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('SocketException: Network is unreachable'),
          candidateUrl: 'https://media.example.test/video.mp4',
        ),
        MediaCandidateFailureKind.networkUnavailable,
      );
    });

    test('classifies ExoPlayer response code and DNS text', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            r'HttpDataSource$InvalidResponseCodeException: Response code: 404',
          ),
          candidateUrl: 'https://cdn.quwoquan.com/media/video/s/missing.mp4',
        ),
        MediaCandidateFailureKind.http404,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('java.net.UnknownHostException: Unable to resolve host'),
          candidateUrl: 'https://cdn.quwoquan.com/media/video/s/sample.mp4',
        ),
        MediaCandidateFailureKind.dnsNxdomain,
      );
    });

    test('classifies native trust anchor failures as certificate errors', () {
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'javax.net.ssl.SSLHandshakeException: '
            'Trust anchor for certification path not found.',
          ),
          candidateUrl: 'https://localhost:17100/media/video/s/sample.mp4',
        ),
        MediaCandidateFailureKind.certificateVerifyFailed,
      );
    });

    test('classifies AVFoundation NSURL failures by transport category', () {
      const candidate =
          'https://cdn.alpha.example.invalid:17100/media/video/s/sample.mp4';
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'The operation couldn’t be completed. '
            '(NSURLErrorDomain error -1202.)',
          ),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.certificateVerifyFailed,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('(NSURLErrorDomain error -1003.)'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.dnsNxdomain,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('(NSURLErrorDomain error -1004.)'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.connectionRefused,
      );
    });
  });
}
