import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart';

Map<String, dynamic> _validPatch() => <String, dynamic>{
  'patchId': 'patch-1',
  'patchType': 'new_candidate_hint',
  'userId': 'user-1',
  'targetPostIds': <Object?>['post-1'],
  'reasonCode': 'new_candidates_available',
  'affectedCount': 1,
  'policyDigest':
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'safeToApplyWhileViewing': false,
  'emittedAt': '2026-07-29T12:00:00Z',
};

void main() {
  test('canonical realtime patch decodes without a compatibility branch', () {
    final patch = parseFeedRealtimePatch(_validPatch());

    expect(patch.patchType, FeedRealtimePatchType.newCandidateHint);
    expect(patch.reasonCode, FeedPatchReasonCode.newCandidatesAvailable);
    expect(patch.targetPostIds, <String>['post-1']);
    expect(
      patch.policyDigest,
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    );
  });

  test('unknown enum wire value is rejected instead of mapped to fallback', () {
    final payload = _validPatch()..['patchType'] = 'future_patch';

    expect(() => parseFeedRealtimePatch(payload), throwsFormatException);
  });

  test('policyDigest 只接受精确 canonical 形态或未提供', () {
    const canonical =
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    expect(
      parseFeedRealtimePatch(
        _validPatch()..remove('policyDigest'),
      ).policyDigest,
      isNull,
    );
    expect(
      parseFeedRealtimePatch(
        _validPatch()..['policyDigest'] = null,
      ).policyDigest,
      isNull,
    );
    for (final invalid in <Object?>[
      '',
      'rank-v3',
      ' $canonical',
      '$canonical ',
      'sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      42,
    ]) {
      final payload = _validPatch()..['policyDigest'] = invalid;
      expect(
        () => parseFeedRealtimePatch(payload),
        throwsFormatException,
        reason: 'must reject <$invalid> without coercion or normalization',
      );
    }
  });

  test('mixed targetPostIds list is rejected instead of filtered', () {
    final payload = _validPatch()..['targetPostIds'] = <Object?>['post-1', 2];

    expect(() => parseFeedRealtimePatch(payload), throwsFormatException);
  });

  test('missing required identity is rejected', () {
    final payload = _validPatch()..remove('patchId');

    expect(() => parseFeedRealtimePatch(payload), throwsFormatException);
  });
}
