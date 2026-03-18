class ProfileUpdateProposal {
  const ProfileUpdateProposal({
    required this.proposalId,
    required this.profileVersionRead,
    required this.generatedAt,
    required this.sourceRuns,
    required this.confidence,
    required this.requiresUserConfirm,
    required this.updates,
  });

  final String proposalId;
  final String profileVersionRead;
  final DateTime generatedAt;
  final List<String> sourceRuns;
  final double confidence;
  final bool requiresUserConfirm;
  final List<ProfileUpdateItem> updates;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'proposalId': proposalId,
      'profileVersionRead': profileVersionRead,
      'generatedAt': generatedAt.toIso8601String(),
      'sourceRuns': sourceRuns,
      'confidence': confidence,
      'requiresUserConfirm': requiresUserConfirm,
      'updates': updates.map((item) => item.toJson()).toList(growable: false),
    };
  }

  factory ProfileUpdateProposal.fromJson(Map<String, dynamic> json) {
    final rawUpdates = (json['updates'] as List?) ?? const <dynamic>[];
    final parsedUpdates = rawUpdates
        .whereType<Map>()
        .map((item) => ProfileUpdateItem.fromJson(item.cast<String, dynamic>()))
        .toList(growable: false);
    return ProfileUpdateProposal(
      proposalId: (json['proposalId'] as String?)?.trim() ?? '',
      profileVersionRead: (json['profileVersionRead'] as String?)?.trim() ?? '',
      generatedAt:
          DateTime.tryParse((json['generatedAt'] as String?)?.trim() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0),
      sourceRuns:
          (json['sourceRuns'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      confidence: _asDouble(json['confidence']),
      requiresUserConfirm: json['requiresUserConfirm'] == true,
      updates: parsedUpdates,
    );
  }

  static double _asDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is num) return value.toDouble();
    return 0.0;
  }

  bool get isValid {
    if (proposalId.isEmpty ||
        profileVersionRead.isEmpty ||
        sourceRuns.isEmpty ||
        updates.isEmpty) {
      return false;
    }
    if (confidence < 0 || confidence > 1) return false;
    for (final item in updates) {
      if (!item.isValid) return false;
    }
    return true;
  }
}

class ProfileUpdateItem {
  const ProfileUpdateItem({
    required this.facet,
    required this.path,
    required this.operation,
    required this.newValue,
    required this.oldValueSnapshot,
    required this.reason,
    required this.evidenceRefs,
    required this.itemConfidence,
    required this.riskLevel,
  });

  final String facet;
  final String path;
  final String operation;
  final dynamic newValue;
  final dynamic oldValueSnapshot;
  final String reason;
  final List<String> evidenceRefs;
  final double itemConfidence;
  final String riskLevel;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'facet': facet,
      'path': path,
      'operation': operation,
      'newValue': newValue,
      'oldValueSnapshot': oldValueSnapshot,
      'reason': reason,
      'evidenceRefs': evidenceRefs,
      'itemConfidence': itemConfidence,
      'riskLevel': riskLevel,
    };
  }

  factory ProfileUpdateItem.fromJson(Map<String, dynamic> json) {
    return ProfileUpdateItem(
      facet: (json['facet'] as String?)?.trim() ?? '',
      path: (json['path'] as String?)?.trim() ?? '',
      operation: (json['operation'] as String?)?.trim() ?? '',
      newValue: json['newValue'],
      oldValueSnapshot: json['oldValueSnapshot'],
      reason: (json['reason'] as String?)?.trim() ?? '',
      evidenceRefs:
          (json['evidenceRefs'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      itemConfidence: ProfileUpdateProposal._asDouble(json['itemConfidence']),
      riskLevel: (json['riskLevel'] as String?)?.trim() ?? '',
    );
  }

  bool get isValid {
    if (facet.isEmpty || path.isEmpty || operation.isEmpty || reason.isEmpty) {
      return false;
    }
    if (!const <String>{'set', 'add', 'remove', 'merge'}.contains(operation)) {
      return false;
    }
    if (!const <String>{'low', 'medium', 'high'}.contains(riskLevel)) {
      return false;
    }
    if (itemConfidence < 0 || itemConfidence > 1) return false;
    return true;
  }
}
