// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-data-control');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote preserves one request identity through cancellation',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final createId = 'skill-data-control-create-$nonce';

      final created = await api.skillDataControlCommands
          .createSkillDataControlRequest(
            skillId: _officialSkillId,
            requestedActions: const <SkillDataControlAction>[
              SkillDataControlAction.hideActivityHistory,
            ],
            clientRequestId: createId,
          );
      expect(created.request.requestId, isNotEmpty);
      expect(
        created.request.status,
        SkillDataControlRequestStatus.pendingConfirmation,
      );
      expect(created.request.revision, 1);

      final createReplay = await api.skillDataControlCommands
          .createSkillDataControlRequest(
            skillId: _officialSkillId,
            requestedActions: const <SkillDataControlAction>[
              SkillDataControlAction.hideActivityHistory,
            ],
            clientRequestId: createId,
          );
      expect(createReplay.request.toJson(), created.request.toJson());
      expect(createReplay.replayed, isTrue);

      final beforeConfirm = await api.skillDataControlQueries
          .getSkillDataControlRequest(requestId: created.request.requestId);
      expect(beforeConfirm.toJson(), created.request.toJson());

      final confirmId = 'skill-data-control-cancel-$nonce';
      final cancelled = await api.skillDataControlCommands
          .confirmSkillDataControlRequest(
            requestId: created.request.requestId,
            expectedRevision: created.request.revision,
            confirmed: false,
            clientRequestId: confirmId,
          );
      expect(cancelled.request.requestId, created.request.requestId);
      expect(cancelled.request.status, SkillDataControlRequestStatus.cancelled);
      expect(cancelled.request.revision, greaterThan(created.request.revision));

      final confirmReplay = await api.skillDataControlCommands
          .confirmSkillDataControlRequest(
            requestId: created.request.requestId,
            expectedRevision: created.request.revision,
            confirmed: false,
            clientRequestId: confirmId,
          );
      expect(confirmReplay.request.toJson(), cancelled.request.toJson());
      expect(confirmReplay.replayed, isTrue);

      final readback = await api.skillDataControlQueries
          .getSkillDataControlRequest(requestId: created.request.requestId);
      expect(readback.toJson(), cancelled.request.toJson());

      final events = await api.telemetry.waitForEvents(minimumCount: 6);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        containsAll(<String>[
          AppCloudOperationIds
              .assistantSkillDataControlRequestCreateSkillDataControlRequest,
          AppCloudOperationIds
              .assistantSkillDataControlRequestConfirmSkillDataControlRequest,
          AppCloudOperationIds
              .assistantSkillDataControlRequestGetSkillDataControlRequest,
        ]),
      );
    },
  );
}
