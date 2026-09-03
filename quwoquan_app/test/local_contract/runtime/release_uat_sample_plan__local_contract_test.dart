import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import '../../support/runtime/patrol/patrol_app_uat_case_evidence_payload.dart';
import '../../support/runtime/patrol/release_uat_sample_plan.dart';

const _entries = <String>[
  'feed',
  'search',
  'recommendation',
  'direct_or_object_route',
];
const _carriers = <String>['homepage', 'article', 'image', 'video'];

void main() {
  test('exact Data plan plus runtime mapping produces 16 exact slots', () {
    final plan = _plan();
    final exactBytes = utf8.encode(jsonEncode(plan));
    final matrix = parseReleaseUatSampleMatrix(
      encodedPlan: base64Encode(exactBytes),
      encodedRuntimeBinding: base64Encode(utf8.encode(jsonEncode(_binding()))),
    );

    expect(matrix.exactPlanBytes, exactBytes);
    expect(matrix.samples, hasLength(4));
    expect(matrix.slots, hasLength(16));
    expect(matrix.slots.map((slot) => slot.captureId).toSet(), hasLength(16));
    expect(matrix.slots.first.sample.runtimeObjectId, 'runtime-homepage');
    expect(
      matrix.slots.last.runnerIdentity,
      'qwq.content_consumer.direct_or_object_route.video.v1',
    );
  });

  test('case evidence payload preserves exact slot identity', () {
    final matrix = parseReleaseUatSampleMatrix(
      encodedPlan: base64Encode(utf8.encode(jsonEncode(_plan()))),
      encodedRuntimeBinding: base64Encode(utf8.encode(jsonEncode(_binding()))),
    );
    final slot = matrix.slots.first;
    final page = buildPatrolAppUatPageEvidenceReady(
      slot: slot,
      route: '/entity/runtime-homepage',
      terminalKey: 'homepage-detail-page',
    );
    final marker = buildPassedPatrolAppUatCaseEvidence(
      slot: slot,
      targetKind: 'object',
      startedAt: '2026-08-31T00:00:00Z',
      completedAt: '2026-08-31T00:00:01Z',
    );

    expect(page['captureId'], slot.captureId);
    expect(marker['sampleId'], slot.sample.sampleId);
    expect(marker['objectId'], slot.sample.objectId);
    expect(marker['carrier'], slot.sample.carrier);
    expect(marker['specRef'], slot.specRef);
    expect(marker['runnerIdentity'], slot.runnerIdentity);
    expect(marker['pageEvidence'], <String, String>{
      'status': 'host_captured',
      'captureId': slot.captureId,
    });
    expect(
      () => buildBlockedPatrolAppUatCaseEvidence(
        slot: slot,
        reasonCode: 'query failed',
        timestamp: '2026-08-31T00:00:00Z',
      ),
      throwsArgumentError,
    );
  });

  test('runtime identity drift fails closed', () {
    final binding = _binding();
    (binding['samples']! as List<Object?>)[0] = <String, String>{
      'sampleId': 'baseline-homepage-001',
      'carrier': 'homepage',
      'sourceObjectId': 'wrong-source',
      'readObjectId': 'runtime-homepage',
    };
    expect(
      () => parseReleaseUatSampleMatrix(
        encodedPlan: base64Encode(utf8.encode(jsonEncode(_plan()))),
        encodedRuntimeBinding: base64Encode(utf8.encode(jsonEncode(binding))),
      ),
      throwsFormatException,
    );
  });

  test('non-required or incomplete matrix fails closed', () {
    final plan = _plan();
    (plan['entryCarrierCells']!
        as List<Map<String, String>>)[0] = <String, String>{
      'entry': 'feed',
      'carrier': 'homepage',
      'applicability': 'not_applicable',
      'reasonCode': 'NOT_SUPPORTED',
    };
    expect(
      () => parseReleaseUatSampleMatrix(
        encodedPlan: base64Encode(utf8.encode(jsonEncode(plan))),
        encodedRuntimeBinding: base64Encode(
          utf8.encode(jsonEncode(_binding())),
        ),
      ),
      throwsFormatException,
    );
  });
}

Map<String, Object?> _plan() => <String, Object?>{
  'schema': 'quwoquan_data.release_uat_sample_plan',
  'releaseId': 'release-a',
  'sampleCount': 4,
  'samples': <Map<String, String>>[
    for (final carrier in _carriers)
      <String, String>{
        'sampleId': 'baseline-$carrier-001',
        'carrier': carrier,
        'objectId': 'source-$carrier',
        'objectRef': carrier == 'homepage'
            ? 'objects/entities/source-homepage'
            : 'objects/posts/$carrier/source-$carrier',
        'objectDigest': 'sha256:${'a' * 64}',
      },
  ],
  'entryCarrierCells': <Map<String, String>>[
    for (final entry in _entries)
      for (final carrier in _carriers)
        <String, String>{
          'entry': entry,
          'carrier': carrier,
          'applicability': 'required',
          'specRef': 'spec.md#gwt-004',
          'runnerClass': 'qwq.content_consumer.$entry.$carrier.v1',
        },
  ],
};

Map<String, Object?> _binding() => <String, Object?>{
  'schema': 'quwoquan_ops.app_uat_sample_runtime_binding.v1',
  'releaseId': 'release-a',
  'samples': <Map<String, String>>[
    for (final carrier in _carriers)
      <String, String>{
        'sampleId': 'baseline-$carrier-001',
        'carrier': carrier,
        'sourceObjectId': 'source-$carrier',
        'readObjectId': 'runtime-$carrier',
      },
  ],
};
