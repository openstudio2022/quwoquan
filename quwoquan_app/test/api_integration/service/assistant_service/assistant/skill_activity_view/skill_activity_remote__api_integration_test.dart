// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-activity');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote projects one cancelled data-control activity',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final created = await api.skillDataControlCommands
          .createSkillDataControlRequest(
            skillId: _officialSkillId,
            requestedActions: const <SkillDataControlAction>[
              SkillDataControlAction.hideActivityHistory,
            ],
            clientRequestId: 'skill-activity-create-$nonce',
          );
      final cancelled = await api.skillDataControlCommands
          .confirmSkillDataControlRequest(
            requestId: created.request.requestId,
            expectedRevision: created.request.revision,
            confirmed: false,
            clientRequestId: 'skill-activity-cancel-$nonce',
          );
      expect(cancelled.request.status, SkillDataControlRequestStatus.cancelled);

      SkillActivityView? projected;
      for (var attempt = 0; attempt < 8 && projected == null; attempt += 1) {
        final activities = await api.skillActivities.listSkillActivities(
          skillId: _officialSkillId,
        );
        for (final item in activities.items) {
          if (item.dataControlRequestId == created.request.requestId) {
            projected = item;
            break;
          }
        }
        if (projected == null) {
          await Future<void>.delayed(const Duration(milliseconds: 250));
        }
      }

      final activity = projected;
      expect(activity, isNotNull);
      final requiredActivity = activity!;
      expect(requiredActivity.activityKind, SkillActivityKind.dataControl);
      expect(requiredActivity.status, 'cancelled');
      expect(requiredActivity.sourceRevision, cancelled.request.revision);
      expect(requiredActivity.failureCode, isNull);

      final events = await api.telemetry.waitForEvents(minimumCount: 3);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        contains(
          AppCloudOperationIds.assistantSkillActivityViewListSkillActivities,
        ),
      );
    },
  );
}
