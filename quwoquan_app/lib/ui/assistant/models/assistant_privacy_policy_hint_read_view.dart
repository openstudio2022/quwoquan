// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `openContext.hints.privacyPolicy` 为开放配置 JSON。

import 'package:quwoquan_app/assistant/capabilities/capabilities.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';

/// 私助打开上下文里 `privacyPolicy` 子树的只读投影与默认表。
class AssistantPrivacyPolicyHintReadView {
  AssistantPrivacyPolicyHintReadView._(this._raw);

  final Map<String, dynamic> _raw;

  static Map<String, dynamic> defaultPrivacyPolicyMap() => <String, dynamic>{
    'webAccessMode': 'limited',
    'allowedCapabilities': AssistantCapabilityCatalog.defaultCatalog,
    'allowedProviders': <String>[
      'page_context',
      'conversation',
      'memory',
      'web',
    ],
    'blockedProviders': <String>[],
    'allowedPageTypes': <String>[
      'discovery',
      'circles',
      'create',
      'chat',
      'home',
    ],
    'maxWebRounds': 1,
    'redactBeforeWeb': true,
    'blockedReferenceHosts':
        AppConceptConstants.assistantReferenceHostBlocklist,
  };

  factory AssistantPrivacyPolicyHintReadView.fromOpenContextHints(
    Map<String, dynamic> hints,
  ) {
    final nested = (hints['privacyPolicy'] as Map?)?.cast<String, dynamic>();
    if (nested == null || nested.isEmpty) {
      return AssistantPrivacyPolicyHintReadView._(
        Map<String, dynamic>.from(defaultPrivacyPolicyMap()),
      );
    }
    return AssistantPrivacyPolicyHintReadView._(
      Map<String, dynamic>.from(nested),
    );
  }

  List<String> _trimmedStringList(String key) {
    final raw = _raw[key];
    if (raw is! List) return <String>[];
    return raw
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: true);
  }

  List<String> get allowedProviders => _trimmedStringList('allowedProviders');

  List<String> get blockedProviders => _trimmedStringList('blockedProviders');

  Map<String, dynamic> copyWithProviderLists({
    required List<String> allowedProviders,
    required List<String> blockedProviders,
  }) => <String, dynamic>{
    ..._raw,
    'allowedProviders': allowedProviders,
    'blockedProviders': blockedProviders,
  };
}
