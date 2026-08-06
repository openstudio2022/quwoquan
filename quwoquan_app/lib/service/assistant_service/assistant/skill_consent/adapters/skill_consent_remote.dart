import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSkillConsentInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// SkillConsent 的 production generated-client adapter。
final class RemoteAssistantSkillConsentAdapter
    implements AssistantSkillConsentFacet {
  const RemoteAssistantSkillConsentAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSkillConsentInvocationContextFactory invocationContext;

  @override
  Future<List<SkillConsent>> listConsents() async {
    final result = await client.assistantSkillConsentListConsents(
      const ListSkillConsentsQuery(),
      context: invocationContext(AssistantRequestPageIds.listConsents),
    );
    return result.items;
  }

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    final receipt = await client.assistantSkillConsentGrantSkillConsent(
      GrantSkillConsentRequest(skillId: skillId, grantedScopes: grantedScopes),
      context: invocationContext(
        AssistantRequestPageIds.grantSkillConsent,
        idempotencyKey: clientRequestId,
      ),
    );
    return receipt.consent;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    await client.assistantSkillConsentRevokeSkillConsent(
      RevokeSkillConsentRequest(skillId: skillId),
      context: invocationContext(
        AssistantRequestPageIds.revokeSkillConsent,
        idempotencyKey: clientRequestId,
      ),
    );
  }
}
