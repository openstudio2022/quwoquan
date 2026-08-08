// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
// readiness_case: skill_subscription_create_skill_subscription_app_api
// readiness_case: skill_subscription_get_skill_subscription_app_api
// readiness_case: skill_subscription_list_skill_subscriptions_app_api
// readiness_case: skill_subscription_update_skill_subscription_status_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialTravelCompanionSkillId = 'travel_companion';
const _officialTravelCompanionDomainId = 'travel';
const _travelCompanionTimezone = 'Asia/Shanghai';
const _travelCompanionCron = '0 8 * * *';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-subscription');
  });
  tearDownAll(() => harness?.close());

  test(
    'official travel_companion subscription replays and archives without changing Setting or Consent',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final createRequestId = 'skill-subscription-create-$nonce';
      final settingsBefore = _settingSnapshot(
        await api.skillUserSettings.listSkillUserSettings(),
      );
      final consentsBefore = _consentSnapshot(
        await api.skillConsents.listConsents(),
      );
      SkillSubscriptionWire? created;
      var archivedForCleanup = false;

      try {
        created = await api.skillSubscriptions.createSkillSubscription(
          skillId: _officialTravelCompanionSkillId,
          domainId: _officialTravelCompanionDomainId,
          tagRefs: const <String>['travel'],
          rawText: 'daily travel companion reminder',
          queries: const <String>['travel weather', 'travel transit'],
          cron: _travelCompanionCron,
          timezone: _travelCompanionTimezone,
          clientRequestId: createRequestId,
        );
        expect(created.subscriptionId, isNotEmpty);
        expect(created.skillId, _officialTravelCompanionSkillId);
        expect(created.domainId, _officialTravelCompanionDomainId);
        expect(created.status, SkillSubscriptionStatus.active);
        expect(created.trigger.cron, _travelCompanionCron);
        expect(created.trigger.timezone, _travelCompanionTimezone);
        _expectUtcNextAttempt(created);

        final replayed = await api.skillSubscriptions.createSkillSubscription(
          skillId: _officialTravelCompanionSkillId,
          domainId: _officialTravelCompanionDomainId,
          tagRefs: const <String>['travel'],
          rawText: 'daily travel companion reminder',
          queries: const <String>['travel weather', 'travel transit'],
          cron: _travelCompanionCron,
          timezone: _travelCompanionTimezone,
          clientRequestId: createRequestId,
        );
        expect(replayed.toWire(), created.toWire());

        final fetched = await api.skillSubscriptions.getSkillSubscription(
          subscriptionId: created.subscriptionId,
        );
        expect(fetched.subscriptionId, created.subscriptionId);
        expect(fetched.owner.ownerId, api.session.ownerId);
        expect(fetched.status, SkillSubscriptionStatus.active);
        _expectUtcNextAttempt(fetched);

        final active = await api.skillSubscriptions.listSkillSubscriptions(
          status: SkillSubscriptionStatus.active.wireName,
        );
        expect(
          active.map((item) => item.subscriptionId),
          contains(created.subscriptionId),
        );

        final archived = await api.skillSubscriptions
            .updateSkillSubscriptionStatus(
              subscriptionId: created.subscriptionId,
              status: SkillSubscriptionStatus.archived.wireName,
              clientRequestId: 'skill-subscription-archive-$nonce',
            );
        archivedForCleanup =
            archived.status == SkillSubscriptionStatus.archived;
        expect(archived.status, SkillSubscriptionStatus.archived);

        final archivedItems = await api.skillSubscriptions
            .listSkillSubscriptions(
              status: SkillSubscriptionStatus.archived.wireName,
            );
        expect(
          archivedItems.map((item) => item.subscriptionId),
          contains(created.subscriptionId),
        );

        final settingsAfter = _settingSnapshot(
          await api.skillUserSettings.listSkillUserSettings(),
        );
        final consentsAfter = _consentSnapshot(
          await api.skillConsents.listConsents(),
        );
        expect(settingsAfter, settingsBefore);
        expect(consentsAfter, consentsBefore);

        final events = await api.telemetry.waitForEvents(minimumCount: 11);
        expect(events.every((event) => event.succeeded), isTrue);
        expect(
          events.map((event) => event.canonicalOperationId),
          containsAll(<String>[
            AppCloudOperationIds
                .assistantSkillSubscriptionCreateSkillSubscription,
            AppCloudOperationIds.assistantSkillSubscriptionGetSkillSubscription,
            AppCloudOperationIds
                .assistantSkillSubscriptionListSkillSubscriptions,
            AppCloudOperationIds
                .assistantSkillSubscriptionUpdateSkillSubscriptionStatus,
          ]),
        );
      } finally {
        if (created != null && !archivedForCleanup) {
          await api.skillSubscriptions.updateSkillSubscriptionStatus(
            subscriptionId: created.subscriptionId,
            status: SkillSubscriptionStatus.archived.wireName,
            clientRequestId: 'skill-subscription-cleanup-$nonce',
          );
        }
      }
    },
  );
}

Map<String, Object?> _settingSnapshot(List<SkillUserSetting> settings) {
  return <String, Object?>{
    for (final setting in settings) setting.id: setting.toJson(),
  };
}

Map<String, Object?> _consentSnapshot(List<SkillConsent> consents) {
  return <String, Object?>{
    for (final consent in consents) consent.id: consent.toJson(),
  };
}

void _expectUtcNextAttempt(SkillSubscriptionWire subscription) {
  final raw = subscription.deliveryState.nextAttemptAt;
  expect(raw, isNotEmpty);
  final parsed = DateTime.tryParse(raw);
  expect(parsed, isNotNull);
  expect(parsed?.isUtc, isTrue);
}
