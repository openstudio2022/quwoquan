import 'package:quwoquan_app/personal_assistant/retrieval/privacy_policy.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';

class AssistentRetrievalRouter {
  const AssistentRetrievalRouter();

  AssistentRetrievalRouteDecision decide({
    required AssistentRetrievalRequest request,
    required Map<String, List<String>> providerCapabilities,
  }) {
    final capabilities = request.requestedCapabilities;
    final policy = AssistentPrivacyPolicy.fromInputs(
      privacyProfile: request.privacyProfile,
      contextScopeHint: <String, dynamic>{
        ...request.contextScopeHint,
        'privacyPolicy': request.privacyPolicy,
      },
      fallbackCapabilities: capabilities,
    );
    final approvedCapabilities = capabilities.where(policy.allowsCapability).toList(growable: false);

    final providers = <String>[];
    for (final capability in approvedCapabilities) {
      for (final entry in providerCapabilities.entries) {
        if (entry.value.contains(capability) && !providers.contains(entry.key)) {
          if (!policy.allowsProvider(entry.key)) {
            continue;
          }
          providers.add(entry.key);
        }
      }
    }

    if (providers.isEmpty &&
        request.providerHint != null &&
        request.providerHint!.trim().isNotEmpty) {
      final hinted = request.providerHint!.trim();
      if (providerCapabilities.containsKey(hinted) && policy.allowsProvider(hinted)) {
        providers.add(hinted);
      }
    }

    final maxRounds = policy.maxWebRounds <= 0 ? 0 : policy.maxWebRounds;
    return AssistentRetrievalRouteDecision(
      providerSequence: providers,
      capabilitySequence: approvedCapabilities,
      maxRounds: maxRounds,
      decisionReasons: <String, dynamic>{
        'webAccessMode': policy.webAccessMode,
        'requestedCapabilities': capabilities,
        'approvedCapabilities': approvedCapabilities,
        'maxWebRounds': policy.maxWebRounds,
        'providerHint': request.providerHint?.trim() ?? '',
      },
    );
  }
}

