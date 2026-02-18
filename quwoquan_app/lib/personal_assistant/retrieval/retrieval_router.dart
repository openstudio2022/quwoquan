import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/privacy_policy.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';

class AssistentRetrievalRouter {
  const AssistentRetrievalRouter();

  AssistentRetrievalRouteDecision decide({
    required AssistentRetrievalRequest request,
    required Map<String, List<String>> providerCapabilities,
  }) {
    final capabilities = request.requestedCapabilities.isNotEmpty
        ? request.requestedCapabilities
        : _inferCapabilitiesFromQuery(request.query);
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

    if (providers.isEmpty && policy.allowsProvider('web') && providerCapabilities.containsKey('web')) {
      providers.add('web');
    }
    if (providers.isEmpty &&
        policy.allowsProvider('conversation') &&
        providerCapabilities.containsKey('conversation')) {
      providers.add('conversation');
    }

    final maxRounds = _inferNeedsRealtime(request.query)
        ? (policy.webAccessMode == 'allow' ? 3 : 2)
        : 2;
    return AssistentRetrievalRouteDecision(
      providerSequence: providers,
      capabilitySequence: approvedCapabilities,
      maxRounds: maxRounds,
      decisionReasons: <String, dynamic>{
        'webAccessMode': policy.webAccessMode,
        'requestedCapabilities': capabilities,
        'approvedCapabilities': approvedCapabilities,
        'maxWebRounds': policy.maxWebRounds,
      },
    );
  }

  List<String> _inferCapabilitiesFromQuery(String query) {
    final lowered = query.toLowerCase();
    final capabilities = <String>[
      AssistentCapabilityCatalog.currentPage,
      AssistentCapabilityCatalog.chatRecent,
      AssistentCapabilityCatalog.chatLongterm,
    ];
    if (_inferNeedsRealtime(lowered)) {
      capabilities.add(AssistentCapabilityCatalog.webSearch);
    }
    if (lowered.contains('评论')) {
      capabilities.add(AssistentCapabilityCatalog.pageComments);
    }
    if (lowered.contains('上次') || lowered.contains('历史') || lowered.contains('之前')) {
      capabilities.add(AssistentCapabilityCatalog.behaviorTimeline);
    }
    return capabilities;
  }

  bool _inferNeedsRealtime(String query) {
    final lowered = query.toLowerCase();
    return lowered.contains('天气') ||
        lowered.contains('新闻') ||
        lowered.contains('实时') ||
        lowered.contains('最新') ||
        lowered.contains('行情');
  }
}

