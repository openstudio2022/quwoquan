import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// SkillConsent 的对象级 command/query facade。
abstract class AssistantSkillConsentFacet {
  Future<List<SkillConsent>> listConsents();

  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  });

  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  });
}
