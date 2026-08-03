import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class LocalCircleGroupSnapshotRecord {
  const LocalCircleGroupSnapshotRecord({
    required this.groupId,
    required this.circleId,
    required this.name,
    this.description = '',
    this.circleName = '',
    required this.groupType,
    required this.visibility,
    this.conversationId = '',
    this.memberCount = 0,
    required this.updatedAt,
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

  factory LocalCircleGroupSnapshotRecord.fromGroupSlice(
    CircleGroupSlice group, {
    String circleName = '',
  }) {
    return LocalCircleGroupSnapshotRecord(
      groupId: group.groupId,
      circleId: group.circleId,
      name: group.name,
      description: group.description ?? '',
      circleName: circleName.trim(),
      groupType: switch (group.groupType) {
        CircleGroupType.publicGroup => 'public_group',
        CircleGroupType.selfBuilt => 'self_built',
        CircleGroupType.orgNode => 'org_node',
      },
      visibility: group.visibility.wireName,
      conversationId: group.conversationId ?? '',
      memberCount: group.memberCount,
      updatedAt: group.updatedAt.toIso8601String(),
    );
  }

  factory LocalCircleGroupSnapshotRecord.fromStorageMap(
    Map<String, Object?> map,
  ) {
    return LocalCircleGroupSnapshotRecord(
      groupId: _requiredString(map, 'groupId'),
      circleId: _requiredString(map, 'circleId'),
      name: _requiredString(map, 'name'),
      description: _string(map['description']),
      circleName: _string(map['circleName']),
      groupType: _requiredString(map, 'groupType'),
      visibility: _requiredString(map, 'visibility'),
      conversationId: _string(map['conversationId']),
      memberCount: _nonNegativeInt(map, 'memberCount'),
      updatedAt: _requiredString(map, 'updatedAt'),
      highlightText: _optionalString(map['highlightText']),
      matchedField: _optionalString(map['matchedField']),
    );
  }

  Map<String, Object?> toStorageMap() {
    return <String, Object?>{
      'groupId': groupId,
      'circleId': circleId,
      'name': name,
      'description': description,
      'circleName': circleName,
      'groupType': groupType,
      'visibility': visibility,
      'conversationId': conversationId,
      'memberCount': memberCount,
      'updatedAt': updatedAt,
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

int _nonNegativeInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! num || value < 0) {
    throw FormatException('$key must be a non-negative number');
  }
  return value.toInt();
}

String _requiredString(Map<String, Object?> map, String key) {
  final value = _string(map[key]);
  if (value.isEmpty) {
    throw FormatException('$key must be non-empty');
  }
  return value;
}

String _string(Object? value) => value?.toString().trim() ?? '';

String? _optionalString(Object? value) {
  final text = _string(value);
  return text.isEmpty ? null : text;
}
