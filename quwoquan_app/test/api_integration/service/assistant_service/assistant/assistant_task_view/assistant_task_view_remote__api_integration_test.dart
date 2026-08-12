// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t2
// readiness_case: assistant_task_view_list_assistant_tasks_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';
const _officialDomainId = 'travel';
const _timezone = 'Asia/Shanghai';
const _cron = '0 8 * * *';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('assistant-task-view');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote derives canonical tasks from subscription and active catalog',
    () async {
      final api = harness!;
      final catalog = await api.skillCatalog.getSkillCatalogItem(
        skillId: _officialSkillId,
      );
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      SkillSubscriptionWire? subscription;
      var archivedForCleanup = false;

      try {
        subscription = await api.skillSubscriptions.createSkillSubscription(
          skillId: _officialSkillId,
          domainId: _officialDomainId,
          tagRefs: const <String>['travel'],
          rawText: 'daily travel companion task',
          queries: const <String>['travel weather', 'travel transit'],
          cron: _cron,
          timezone: _timezone,
          clientRequestId: 'assistant-task-create-$nonce',
        );

        final inProgress = await api.tasks.listAssistantTasks(
          status: 'in_progress',
          limit: 20,
        );
        final activeTask = inProgress.singleWhere(
          (task) => task.taskId == subscription!.subscriptionId,
        );
        expect(activeTask.title, catalog.item.displayName);
        expect(activeTask.description, catalog.item.description);
        expect(activeTask.status, 'in_progress');
        expect(activeTask.sourceSkillId, _officialSkillId);
        expect(activeTask.dueAt, subscription.deliveryState.nextAttemptAt);
        expect(DateTime.tryParse(activeTask.updatedAt), isNotNull);

        subscription = await api.skillSubscriptions
            .updateSkillSubscriptionStatus(
              subscriptionId: subscription.subscriptionId,
              status: SkillSubscriptionStatus.paused.wireName,
              clientRequestId: 'assistant-task-pause-$nonce',
            );
        final pending = await api.tasks.listAssistantTasks(
          status: 'pending',
          limit: 20,
        );
        final pausedTask = pending.singleWhere(
          (task) => task.taskId == subscription!.subscriptionId,
        );
        expect(pausedTask.title, catalog.item.displayName);
        expect(pausedTask.status, 'pending');
        expect(pausedTask.dueAt, isNull);

        subscription = await api.skillSubscriptions
            .updateSkillSubscriptionStatus(
              subscriptionId: subscription.subscriptionId,
              status: SkillSubscriptionStatus.archived.wireName,
              clientRequestId: 'assistant-task-archive-$nonce',
            );
        archivedForCleanup =
            subscription.status == SkillSubscriptionStatus.archived;
        final completed = await api.tasks.listAssistantTasks(
          status: 'completed',
          limit: 20,
        );
        final archivedTask = completed.singleWhere(
          (task) => task.taskId == subscription!.subscriptionId,
        );
        expect(archivedTask.status, 'completed');
        expect(archivedTask.dueAt, isNull);

        final events = await api.telemetry.waitForEvents(minimumCount: 7);
        expect(events.every((event) => event.succeeded), isTrue);
        expect(
          events.map((event) => event.canonicalOperationId),
          containsAll(<String>[
            AppCloudOperationIds.assistantSkillCatalogGetSkillCatalogItem,
            AppCloudOperationIds
                .assistantSkillSubscriptionCreateSkillSubscription,
            AppCloudOperationIds
                .assistantSkillSubscriptionUpdateSkillSubscriptionStatus,
            AppCloudOperationIds.assistantAssistantTaskViewListAssistantTasks,
          ]),
        );
      } finally {
        if (subscription != null && !archivedForCleanup) {
          await api.skillSubscriptions.updateSkillSubscriptionStatus(
            subscriptionId: subscription.subscriptionId,
            status: SkillSubscriptionStatus.archived.wireName,
            clientRequestId: 'assistant-task-cleanup-$nonce',
          );
        }
      }
    },
  );
}
