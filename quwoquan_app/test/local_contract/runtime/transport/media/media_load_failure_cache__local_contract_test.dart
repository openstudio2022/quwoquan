import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';

class _StatusError implements Exception {
  _StatusError(this.statusCode);
  final int statusCode;

  @override
  String toString() =>
      'HttpExceptionWithStatus($statusCode): Invalid statusCode: $statusCode';
}

void main() {
  late MediaLoadFailureCache cache;
  late DateTime now;

  setUp(() {
    now = DateTime.utc(2026, 7, 16, 12);
    cache = MediaLoadFailureCache(
      defaultCooldown: const Duration(seconds: 60),
      now: () => now,
    );
  });

  test('404 写入负缓存后冷却期内 shouldSkipNetwork', () {
    const identity = 'https://cdn.alpha.quwoquan.com:17100/media/image/s/x.png';
    cache.recordFailure(
      identity,
      error: _StatusError(404),
      candidateUrl: identity,
    );
    expect(cache.shouldSkipNetwork(identity), isTrue);
    expect(
      cache.activeFailure(identity)?.kind,
      MediaCandidateFailureKind.http404,
    );
  });

  test('冷却到期后允许再试', () {
    const identity = 'https://cdn.alpha.quwoquan.com:17100/media/image/s/y.png';
    cache.recordFailure(
      identity,
      error: _StatusError(404),
      candidateUrl: identity,
    );
    now = now.add(const Duration(seconds: 61));
    expect(cache.shouldSkipNetwork(identity), isFalse);
  });

  test('同 identity 失败日志只允许一次', () {
    const identity = 'https://cdn.alpha.quwoquan.com:17100/media/image/s/z.png';
    expect(cache.shouldLogFailure(identity), isTrue);
    expect(cache.shouldLogFailure(identity), isFalse);
  });

  test('classifyMediaCandidateLoadFailure 识别 404/5xx', () {
    expect(
      classifyMediaCandidateLoadFailure(_StatusError(404)),
      MediaCandidateFailureKind.http404,
    );
    expect(
      classifyMediaCandidateLoadFailure(_StatusError(503)),
      MediaCandidateFailureKind.http5xx,
    );
    expect(
      classifyMediaCandidateLoadFailure(_StatusError(403)),
      MediaCandidateFailureKind.http4xx,
    );
  });
}
