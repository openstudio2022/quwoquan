// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feedback-ingestion-sampling/spec.md#gwt-001
// readiness_case: content_behavior_fact_report_behaviors_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;
  var harnessCreated = false;

  setUpAll(() async {
    harness = await ContentApiContractHarness.create();
    harnessCreated = true;
  });
  tearDownAll(() async {
    if (harnessCreated) {
      await harness.close();
    }
  });

  ContentBehaviorEventWire event(
    BehaviorEventType action,
    String suffix, {
    String? state,
    double? duration,
  }) => ContentBehaviorEventWire(
    clientEventId:
        'content-behavior-$suffix-${DateTime.now().microsecondsSinceEpoch}',
    occurredAt: DateTime.now().toUtc(),
    contentId: 'fixture_photo_001',
    action: action,
    state: state,
    duration: duration,
    contentType: ContentType.image,
  );

  test('production behavior Remote 接受 typed batch', () async {
    final stopwatch = Stopwatch()..start();
    await harness.behaviors.reportBehaviors(
      ReportContentBehaviorsCommand(
        events: <ContentBehaviorEventWire>[
          event(BehaviorEventType.impression, 'impression', state: 'impressed'),
          event(BehaviorEventType.dwell, 'dwell', duration: 12),
        ],
      ),
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(500));
  });

  test('canonical behavior action 集合经 generated client 被接受', () async {
    for (final action in <BehaviorEventType>[
      BehaviorEventType.impression,
      BehaviorEventType.dwell,
      BehaviorEventType.click,
      BehaviorEventType.share,
    ]) {
      await harness.behaviors.reportBehaviors(
        ReportContentBehaviorsCommand(
          events: <ContentBehaviorEventWire>[
            event(
              action,
              action.name,
              state: action == BehaviorEventType.impression
                  ? 'impressed'
                  : null,
              duration: action == BehaviorEventType.dwell ? 12 : null,
            ),
          ],
        ),
      );
    }
  });

  test('like action 经 generated client 被 batch operation 拒绝', () async {
    await expectLater(
      harness.behaviors.reportBehaviors(
        ReportContentBehaviorsCommand(
          events: <ContentBehaviorEventWire>[
            event(BehaviorEventType.like, 'like'),
          ],
        ),
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          400,
        ),
      ),
    );
  });
}
