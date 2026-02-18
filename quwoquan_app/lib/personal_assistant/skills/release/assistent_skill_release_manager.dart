enum AssistentSkillReleaseStage {
  draft,
  canary,
  active,
  deprecated,
  archived,
}

class AssistentSkillReleaseRecord {
  const AssistentSkillReleaseRecord({
    required this.skillId,
    required this.version,
    required this.stage,
    required this.updatedAt,
    this.note = '',
  });

  final String skillId;
  final String version;
  final AssistentSkillReleaseStage stage;
  final DateTime updatedAt;
  final String note;
}

class AssistentSkillReleaseManager {
  final Map<String, AssistentSkillReleaseRecord> _records =
      <String, AssistentSkillReleaseRecord>{};

  void upsert({
    required String skillId,
    required String version,
    required AssistentSkillReleaseStage stage,
    String note = '',
  }) {
    _records[skillId] = AssistentSkillReleaseRecord(
      skillId: skillId,
      version: version,
      stage: stage,
      updatedAt: DateTime.now(),
      note: note,
    );
  }

  AssistentSkillReleaseRecord? bySkillId(String skillId) => _records[skillId];

  List<AssistentSkillReleaseRecord> list() {
    return _records.values.toList(growable: false);
  }
}

