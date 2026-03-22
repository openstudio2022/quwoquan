import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

bool assistantRequestPolicyAlwaysEnabled() => true;

class AssistantRequestPolicy {
  const AssistantRequestPolicy({
    this.isPersonalContentAccessGranted = assistantRequestPolicyAlwaysEnabled,
    this.isAssistantContentIdentityIndexEnabled =
        assistantRequestPolicyAlwaysEnabled,
  });

  final bool Function() isPersonalContentAccessGranted;
  final bool Function() isAssistantContentIdentityIndexEnabled;

  AssistantRunRequest apply(AssistantRunRequest request) {
    final consentGranted = isPersonalContentAccessGranted();
    final identityIndexEnabled = isAssistantContentIdentityIndexEnabled();
    final basePrivacyPolicy = <String, dynamic>{
      ...((request.contextScopeHint['privacyPolicy'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{}),
      ...request.privacyPolicy,
    };
    final allowedProviders = _stringList(basePrivacyPolicy['allowedProviders']);
    final blockedProviders = _stringList(basePrivacyPolicy['blockedProviders']);
    if (!consentGranted) {
      allowedProviders.remove('page_context');
      if (!blockedProviders.contains('page_context')) {
        blockedProviders.add('page_context');
      }
    }
    final nextPrivacyPolicy = <String, dynamic>{
      ...basePrivacyPolicy,
      if (allowedProviders.isNotEmpty) 'allowedProviders': allowedProviders,
      'blockedProviders': blockedProviders,
    };
    final nextContextScope = <String, dynamic>{
      ...request.contextScopeHint,
      'assistantContentAccess': <String, dynamic>{
        'skillId': kPersonalContentAccessSkillId,
        'granted': consentGranted,
        'grantedScope': kPersonalContentAccessSkillId,
      },
      'assistantContentIndex': <String, dynamic>{
        'enabled': identityIndexEnabled,
        'fallbackReason': consentGranted
            ? (identityIndexEnabled ? '' : 'feature_flag_disabled')
            : 'consent_denied',
      },
      'privacyPolicy': nextPrivacyPolicy,
    };
    if (!consentGranted) {
      nextContextScope.remove('behaviorTimeline');
    }
    return AssistantRunRequest(
      messages: request.messages,
      sessionId: request.sessionId,
      userId: request.userId,
      profileSubjectId: request.profileSubjectId,
      subAccountId: request.subAccountId,
      personaContextVersion: request.personaContextVersion,
      deviceProfile: request.deviceProfile,
      deviceModel: request.deviceModel,
      deviceOs: request.deviceOs,
      gpsLocation: request.gpsLocation,
      channel: request.channel,
      traceId: request.traceId,
      maxIterations: request.maxIterations,
      capabilityCatalog: request.capabilityCatalog,
      contextScopeHint: nextContextScope,
      privacyProfile: request.privacyProfile,
      privacyPolicy: nextPrivacyPolicy,
      userProfileSnapshot: request.userProfileSnapshot,
      sourceSurfaceId: request.sourceSurfaceId,
      sourceQuery: request.sourceQuery,
      fromGlobalSearch: request.fromGlobalSearch,
      rewriteInstruction: request.rewriteInstruction,
    );
  }

  List<String> _stringList(Object? raw) {
    if (raw is! List) return <String>[];
    return raw
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: true);
  }
}
