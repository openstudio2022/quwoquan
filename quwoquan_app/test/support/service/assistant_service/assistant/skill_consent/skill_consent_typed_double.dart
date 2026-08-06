import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantSkillConsentFacet implements AssistantSkillConsentFacet {
  final List<SkillConsent> _consents = <SkillConsent>[];

  @override
  Future<List<SkillConsent>> listConsents() async =>
      List<SkillConsent>.unmodifiable(_consents);

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final consent = SkillConsent(
      id: 'consent:$skillId',
      accountId: 'fixture_assistant',
      skillId: skillId,
      grantedScopes: List<String>.unmodifiable(grantedScopes),
      grantedAt: now,
      revokedAt: null,
      granted: true,
    );
    _consents
      ..removeWhere((item) => item.skillId == skillId)
      ..add(consent);
    return consent;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    _consents.removeWhere((item) => item.skillId == skillId);
  }
}
