// spec_ref: specs/feature-tree/circle-community/in-circle-recommendation-loop/behavior-ingestion/spec.md#gwt-001

/// CircleBehaviorFact production Remote API source contract.
///
/// The runner creates its Circle through the public aggregate command, appends
/// only through the object Remote, and observes the real projection through the
/// public Circle query. It does not seed storage or inject a test transport.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';

void main() {
  late CircleApiContractHarness harness;

  setUpAll(() async {
    harness = await CircleApiContractHarness.create();
    await harness.loginDisposableAccount('behavior-fact');
  });
  tearDownAll(() => harness.close());

  test(
    'production Remote appends one trusted fact and rejects a conflicting replay',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final created = await harness.withIdempotencyKey(
        'circle-behavior-parent-$suffix',
        () => harness.lifecycle.createCircle(
          CreateCircleCommand(
            name: 'Behavior fact contract $suffix',
            category: 'community',
          ),
        ),
      );
      final circleId = created.circleId;
      addTearDown(() async {
        await harness.withIdempotencyKey(
          'circle-behavior-cleanup-$circleId',
          () => harness.lifecycle.archiveCircle(
            ArchiveCircleCommand(circleId: circleId),
          ),
        );
      });

      final before = await harness.query.get(
        CircleDetailQuery(circleId: circleId),
      );
      final command = AppendCircleBehaviorFactCommand(
        circleId: circleId,
        eventType: BehaviorEventType.impression,
      );
      final replayKey = 'circle-behavior-append-$suffix';

      await harness.withIdempotencyKey(
        replayKey,
        () => harness.behaviorFacts.append(command),
      );
      await harness.withIdempotencyKey(
        replayKey,
        () => harness.behaviorFacts.append(command),
      );

      await expectLater(
        harness.withIdempotencyKey(
          replayKey,
          () => harness.behaviorFacts.append(
            AppendCircleBehaviorFactCommand(
              circleId: circleId,
              eventType: BehaviorEventType.dwell,
            ),
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.statusCode,
            'statusCode',
            409,
          ),
        ),
      );

      Circle? projected;
      for (var attempt = 0; attempt < 50; attempt += 1) {
        final current = await harness.query.get(
          CircleDetailQuery(circleId: circleId),
        );
        if (current.weeklyActiveCount == before.weeklyActiveCount + 1) {
          projected = current;
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 200));
      }
      expect(
        projected,
        isNotNull,
        reason: 'weekly-active projection must converge',
      );

      final events = await harness.telemetry.waitForEvents(minimumCount: 7);
      final behaviorEvents = events
          .where(
            (event) =>
                event.canonicalOperationId ==
                AppCloudOperationIds
                    .circleCircleBehaviorFactReportCircleBehavior,
          )
          .toList(growable: false);
      expect(behaviorEvents, hasLength(3));
      expect(behaviorEvents.where((event) => event.succeeded), hasLength(2));
      expect(behaviorEvents.where((event) => !event.succeeded), hasLength(1));
      expect(
        behaviorEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}
