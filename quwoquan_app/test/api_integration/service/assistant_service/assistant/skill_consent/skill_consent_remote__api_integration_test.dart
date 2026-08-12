// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-consent');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote grants, replays, reads and revokes one owner consent',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final detail = await api.skillCatalog.getSkillCatalogItem(
        skillId: _officialSkillId,
      );
      final scopes = detail.item.requiredConsentScopes;
      expect(scopes, isNotEmpty);
      expect(
        await api.skillConsents.listConsents(),
        isNot(
          contains(
            isA<SkillConsent>().having(
              (consent) => consent.skillId,
              'skillId',
              _officialSkillId,
            ),
          ),
        ),
      );

      final requestId = 'skill-consent-grant-$nonce';
      var granted = false;
      try {
        final consent = await api.skillConsents.grantSkillConsent(
          skillId: _officialSkillId,
          grantedScopes: scopes,
          clientRequestId: requestId,
        );
        granted = consent.granted;
        expect(consent.accountId, api.session.ownerId);
        expect(consent.skillId, _officialSkillId);
        expect(consent.granted, isTrue);
        expect(consent.grantedScopes, unorderedEquals(scopes));

        final replayed = await api.skillConsents.grantSkillConsent(
          skillId: _officialSkillId,
          grantedScopes: scopes,
          clientRequestId: requestId,
        );
        expect(replayed.toJson(), consent.toJson());

        final active = await api.skillConsents.listConsents();
        expect(
          active
              .singleWhere((item) => item.skillId == _officialSkillId)
              .toJson(),
          consent.toJson(),
        );

        await api.skillConsents.revokeSkillConsent(
          skillId: _officialSkillId,
          clientRequestId: 'skill-consent-revoke-$nonce',
        );
        granted = false;
        final afterRevoke = await api.skillConsents.listConsents();
        expect(
          afterRevoke.map((item) => item.skillId),
          isNot(contains(_officialSkillId)),
        );

        final events = await api.telemetry.waitForEvents(minimumCount: 7);
        expect(events.every((event) => event.succeeded), isTrue);
        expect(
          events.map((event) => event.canonicalOperationId),
          containsAll(<String>[
            AppCloudOperationIds.assistantSkillConsentGrantSkillConsent,
            AppCloudOperationIds.assistantSkillConsentListConsents,
            AppCloudOperationIds.assistantSkillConsentRevokeSkillConsent,
          ]),
        );
      } finally {
        if (granted) {
          await api.skillConsents.revokeSkillConsent(
            skillId: _officialSkillId,
            clientRequestId: 'skill-consent-cleanup-$nonce',
          );
        }
      }
    },
  );
}
