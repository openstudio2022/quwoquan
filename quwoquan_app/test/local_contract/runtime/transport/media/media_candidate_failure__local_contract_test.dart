import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';

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

    test('classifies canonical NSError description with Code= form', () {
      // iOS 真机 PlatformException 常携带 NSError description 形态
      //（`Error Domain=... Code=-1202`，Code 后带等号）；既往正则匹配不到
      // 等号导致证书/DNS/超时全部落入 other → 「这次没能打开内容」。
      const candidate =
          'https://cdn.gamma.quwoquan.com:19100/media/video/s/sample.mp4';
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'PlatformException(VideoError, Failed to load video: '
            'Error Domain=NSURLErrorDomain Code=-1202 '
            '"The certificate for this server is invalid.", null, null)',
          ),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.certificateVerifyFailed,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('Error Domain=NSURLErrorDomain Code=-1003 '
              '"A server with the specified hostname could not be found."'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.dnsNxdomain,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('Error Domain=NSURLErrorDomain Code=-1009 '
              '"The Internet connection appears to be offline."'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.networkUnavailable,
      );
    });

    test('classifies CoreMedia wrapped HTTP status codes', () {
      const candidate =
          'https://cdn.gamma.quwoquan.com:19100/media/video/s/missing.mp4';
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'Error Domain=CoreMediaErrorDomain Code=-12938 '
            '"HTTP 404: File Not Found"',
          ),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.http404,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'Error Domain=CoreMediaErrorDomain Code=-12939 '
            '"byte range length mismatch"',
          ),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.http4xx,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('Error Domain=CoreMediaErrorDomain Code=-12660'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.http4xx,
      );
    });

    test('classifies AVFoundation media-body failures as decoder errors', () {
      const candidate =
          'https://cdn.gamma.quwoquan.com:19100/media/video/s/broken.mp4';
      expect(
        classifyMediaCandidateLoadFailure(
          Exception(
            'Error Domain=AVFoundationErrorDomain Code=-11828 '
            '"Cannot Open" (format not recognized)',
          ),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.decoderInitialization,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('Error Domain=AVFoundationErrorDomain Code=-11821 '
              '"Cannot Decode"'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.decoderInitialization,
      );
      expect(
        classifyMediaCandidateLoadFailure(
          Exception('Error Domain=AVFoundationErrorDomain Code=-11850 '
              '"Operation Stopped" (server incorrectly configured)'),
          candidateUrl: candidate,
        ),
        MediaCandidateFailureKind.http5xx,
      );
    });
  });
}
