class LocalCircleGroupSnapshotRecord {
  const LocalCircleGroupSnapshotRecord({
    required this.groupId,
    required this.circleId,
    this.name = '',
    this.description = '',
    this.circleName = '',
    this.groupType = '',
    this.visibility = '',
    this.conversationId = '',
    this.memberCount = 0,
    this.updatedAt = '',
    this.highlightText,
    this.matchedField,
  });

  final String groupId;
  final String circleId;
  final String name;
  final String description;
  final String circleName;
  final String groupType;
  final String visibility;
  final String conversationId;
  final int memberCount;
  final String updatedAt;
  final String? highlightText;
  final String? matchedField;

  factory LocalCircleGroupSnapshotRecord.fromWireMap(Map<String, dynamic> map) {
    return LocalCircleGroupSnapshotRecord(
      groupId: _firstNonEmpty(<Object?>[
        map['groupId'],
        map['circleGroupId'],
        map['id'],
      ]),
      circleId: _firstNonEmpty(<Object?>[map['circleId'], map['id']]),
      name: _firstNonEmpty(<Object?>[map['name'], map['title']]),
      description: _string(map['description']),
      circleName: _string(map['circleName']),
      groupType: _string(map['groupType']),
      visibility: _string(map['visibility']),
      conversationId: _string(map['conversationId']),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      updatedAt: _string(map['updatedAt']),
      highlightText: _optionalString(map['highlightText']),
      matchedField: _optionalString(map['matchedField']),
    );
  }

  Map<String, dynamic> toWireMap() {
    return <String, dynamic>{
      'groupId': groupId,
      'circleGroupId': groupId,
      'circleId': circleId,
      'name': name,
      if (description.isNotEmpty) 'description': description,
      if (circleName.isNotEmpty) 'circleName': circleName,
      if (groupType.isNotEmpty) 'groupType': groupType,
      if (visibility.isNotEmpty) 'visibility': visibility,
      if (conversationId.isNotEmpty) 'conversationId': conversationId,
      if (memberCount > 0) 'memberCount': memberCount,
      if (updatedAt.isNotEmpty) 'updatedAt': updatedAt,
      if (highlightText != null) 'highlightText': highlightText,
      if (matchedField != null) 'matchedField': matchedField,
    };
  }

  LocalCircleGroupSnapshotRecord copyWith({
    String? groupId,
    String? circleId,
    String? name,
    String? description,
    String? circleName,
    String? groupType,
    String? visibility,
    String? conversationId,
    int? memberCount,
    String? updatedAt,
    String? highlightText,
    String? matchedField,
  }) {
    return LocalCircleGroupSnapshotRecord(
      groupId: groupId ?? this.groupId,
      circleId: circleId ?? this.circleId,
      name: name ?? this.name,
      description: description ?? this.description,
      circleName: circleName ?? this.circleName,
      groupType: groupType ?? this.groupType,
      visibility: visibility ?? this.visibility,
      conversationId: conversationId ?? this.conversationId,
      memberCount: memberCount ?? this.memberCount,
      updatedAt: updatedAt ?? this.updatedAt,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }
}

String _string(Object? value) => value?.toString().trim() ?? '';

String _firstNonEmpty(List<Object?> values) {
  for (final value in values) {
    final text = _string(value);
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

String? _optionalString(Object? value) {
  final text = _string(value);
  return text.isEmpty ? null : text;
}
