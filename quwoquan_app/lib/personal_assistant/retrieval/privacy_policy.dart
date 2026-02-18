class AssistentPrivacyPolicy {
  const AssistentPrivacyPolicy({
    required this.webAccessMode,
    required this.allowedCapabilities,
    required this.blockedCapabilities,
    required this.allowedProviders,
    required this.blockedProviders,
    required this.allowedPageTypes,
    required this.maxWebRounds,
    required this.redactBeforeWeb,
  });

  final String webAccessMode;
  final Set<String> allowedCapabilities;
  final Set<String> blockedCapabilities;
  final Set<String> allowedProviders;
  final Set<String> blockedProviders;
  final Set<String> allowedPageTypes;
  final int maxWebRounds;
  final bool redactBeforeWeb;

  factory AssistentPrivacyPolicy.fromInputs({
    required String privacyProfile,
    required Map<String, dynamic> contextScopeHint,
    required List<String> fallbackCapabilities,
  }) {
    final policyRaw =
        (contextScopeHint['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final normalizedProfile = privacyProfile.trim().toLowerCase();
    final webAccessMode = (policyRaw['webAccessMode'] as String?)?.trim().toLowerCase() ??
        (normalizedProfile == 'strict'
            ? 'deny'
            : normalizedProfile == 'balanced'
                ? 'limited'
                : 'allow');
    final allowedCapabilities = _toStringSet(policyRaw['allowedCapabilities']);
    final blockedCapabilities = _toStringSet(policyRaw['blockedCapabilities']);
    final allowedProviders = _toStringSet(policyRaw['allowedProviders']);
    final blockedProviders = _toStringSet(policyRaw['blockedProviders']);
    final allowedPageTypes = _toStringSet(policyRaw['allowedPageTypes']);
    final maxWebRounds =
        (policyRaw['maxWebRounds'] as int?) ?? (webAccessMode == 'allow' ? 2 : 1);
    final redactBeforeWeb = policyRaw['redactBeforeWeb'] == true || webAccessMode == 'limited';

    final normalizedAllowedCapabilities = allowedCapabilities.isEmpty
        ? fallbackCapabilities.toSet()
        : allowedCapabilities;

    return AssistentPrivacyPolicy(
      webAccessMode: webAccessMode,
      allowedCapabilities: normalizedAllowedCapabilities,
      blockedCapabilities: blockedCapabilities,
      allowedProviders: allowedProviders,
      blockedProviders: blockedProviders,
      allowedPageTypes: allowedPageTypes,
      maxWebRounds: maxWebRounds < 0 ? 0 : maxWebRounds,
      redactBeforeWeb: redactBeforeWeb,
    );
  }

  bool allowsCapability(String capabilityId) {
    if (blockedCapabilities.contains(capabilityId)) return false;
    return allowedCapabilities.contains(capabilityId);
  }

  bool allowsProvider(String providerId) {
    if (blockedProviders.contains(providerId)) return false;
    if (providerId == 'web' && webAccessMode == 'deny') return false;
    if (allowedProviders.isNotEmpty && !allowedProviders.contains(providerId)) return false;
    return true;
  }

  bool allowsPageType(String pageType) {
    if (allowedPageTypes.isEmpty) return true;
    return allowedPageTypes.contains(pageType);
  }

  bool allowsWebRound(int round) {
    if (webAccessMode == 'deny') return false;
    return round <= maxWebRounds;
  }

  String sanitizeQueryForWeb(String query) {
    if (!redactBeforeWeb) return query;
    final compact = query.replaceAll(RegExp(r'\\s+'), ' ').trim();
    var sanitized = compact;
    sanitized = sanitized.replaceAll(
      RegExp(r'1[3-9]\\d{9}'),
      '<redacted_phone>',
    );
    sanitized = sanitized.replaceAll(
      RegExp(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+'),
      '<redacted_email>',
    );
    if (sanitized.length > 96) {
      sanitized = '${sanitized.substring(0, 96)}...';
    }
    return sanitized;
  }

  static Set<String> _toStringSet(dynamic value) {
    if (value is! List) return <String>{};
    return value
        .whereType<String>()
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet();
  }
}

