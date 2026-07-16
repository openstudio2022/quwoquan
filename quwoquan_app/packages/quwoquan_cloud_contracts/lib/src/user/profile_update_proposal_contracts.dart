import '../operation_request_payload.dart';

enum ProfileUpdateProposalSource { persona, assistant, external }

enum ProfileUpdateProposalStatus {
  pending,
  confirmed,
  applied,
  rejected,
  expired,
}

/// Closed value object. Actor, surface, trace and idempotency belong to the
/// invocation context and cannot enter the business command.
final class ProfileChangeSet {
  ProfileChangeSet({
    String? displayName,
    String? bio,
    String? avatarMediaAssetId,
    String? backgroundMediaAssetId,
    this.isPrivate,
    String? isolationLevel,
    String? purposeHint,
  }) : displayName = _optional(displayName),
       bio = _optionalPreservingEmpty(bio),
       avatarMediaAssetId = _optional(avatarMediaAssetId),
       backgroundMediaAssetId = _optional(backgroundMediaAssetId),
       isolationLevel = _optional(isolationLevel),
       purposeHint = _optional(purposeHint) {
    if (this.displayName == null &&
        this.bio == null &&
        this.avatarMediaAssetId == null &&
        this.backgroundMediaAssetId == null &&
        isPrivate == null &&
        this.isolationLevel == null &&
        this.purposeHint == null) {
      throw ArgumentError('ProfileChangeSet requires at least one field');
    }
    if (this.displayName != null && this.displayName!.runes.length > 64) {
      throw ArgumentError.value(displayName, 'displayName', 'max 64 runes');
    }
    if (this.bio != null && this.bio!.runes.length > 500) {
      throw ArgumentError.value(bio, 'bio', 'max 500 runes');
    }
    if (this.isolationLevel != null &&
        !const <String>{
          'open',
          'semi',
          'strict',
        }.contains(this.isolationLevel)) {
      throw ArgumentError.value(
        isolationLevel,
        'isolationLevel',
        'must be open, semi, or strict',
      );
    }
    if (this.purposeHint != null && this.purposeHint!.runes.length > 120) {
      throw ArgumentError.value(purposeHint, 'purposeHint', 'max 120 runes');
    }
  }

  final String? displayName;
  final String? bio;
  final String? avatarMediaAssetId;
  final String? backgroundMediaAssetId;
  final bool? isPrivate;
  final String? isolationLevel;
  final String? purposeHint;

  Map<String, Object?> toWire() => <String, Object?>{
    if (displayName != null) 'displayName': displayName,
    if (bio != null) 'bio': bio,
    if (avatarMediaAssetId != null) 'avatarMediaAssetId': avatarMediaAssetId,
    if (backgroundMediaAssetId != null)
      'backgroundMediaAssetId': backgroundMediaAssetId,
    if (isPrivate != null) 'isPrivate': isPrivate,
    if (isolationLevel != null) 'isolationLevel': isolationLevel,
    if (purposeHint != null) 'purposeHint': purposeHint,
  };
}

final class CreateProfileUpdateProposalCommand {
  CreateProfileUpdateProposalCommand({
    required String personaId,
    required String proposalId,
    required this.source,
    required this.changes,
  }) : personaId = _required(personaId, 'personaId'),
       proposalId = _required(proposalId, 'proposalId');

  final String personaId;
  final String proposalId;
  final ProfileUpdateProposalSource source;
  final ProfileChangeSet changes;
}

final class ConfirmProfileUpdateProposalCommand {
  ConfirmProfileUpdateProposalCommand({
    required String proposalId,
    required this.expectedProposalVersion,
  }) : proposalId = _required(proposalId, 'proposalId') {
    _positive(expectedProposalVersion, 'expectedProposalVersion');
  }

  final String proposalId;
  final int expectedProposalVersion;
}

final class ApplyProfileUpdateProposalCommand {
  ApplyProfileUpdateProposalCommand({
    required String proposalId,
    required this.expectedProposalVersion,
  }) : proposalId = _required(proposalId, 'proposalId') {
    _positive(expectedProposalVersion, 'expectedProposalVersion');
  }

  final String proposalId;
  final int expectedProposalVersion;
}

final class RejectProfileUpdateProposalCommand {
  RejectProfileUpdateProposalCommand({
    required String proposalId,
    required this.expectedProposalVersion,
  }) : proposalId = _required(proposalId, 'proposalId') {
    _positive(expectedProposalVersion, 'expectedProposalVersion');
  }

  final String proposalId;
  final int expectedProposalVersion;
}

final class ProfileUpdateProposalQuery {
  ProfileUpdateProposalQuery({required String proposalId})
    : proposalId = _required(proposalId, 'proposalId');

  final String proposalId;
}

final class ProfileUpdateProposalListQuery {
  ProfileUpdateProposalListQuery({
    required String personaId,
    String? cursor,
    this.limit = 20,
  }) : personaId = _required(personaId, 'personaId'),
       cursor = _optional(cursor) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be in 1..100');
    }
  }

  final String personaId;
  final String? cursor;
  final int limit;
}

final class ProfileUpdateProposalCommandResult {
  const ProfileUpdateProposalCommandResult({
    required this.proposalId,
    required this.version,
    required this.status,
    required this.replayed,
  });

  final String proposalId;
  final int version;
  final ProfileUpdateProposalStatus status;
  final bool replayed;
}

final class ProfileUpdateProposalView {
  const ProfileUpdateProposalView({
    required this.id,
    required this.personaId,
    required this.source,
    required this.status,
    required this.changes,
    required this.reviewedBy,
    required this.targetPersonaExpectedVersion,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    required this.resolvedAt,
  });

  final String id;
  final String personaId;
  final ProfileUpdateProposalSource source;
  final ProfileUpdateProposalStatus status;
  final ProfileChangeSet changes;
  final String? reviewedBy;
  final int? targetPersonaExpectedVersion;
  final int version;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;
}

final class ProfileUpdateProposalSlice {
  const ProfileUpdateProposalSlice({required this.items, this.nextCursor});

  final List<ProfileUpdateProposalView> items;
  final String? nextCursor;
}

abstract interface class ProfileUpdateProposalCommandWriter {
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  );
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  );
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  );
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  );
}

abstract interface class ProfileUpdateProposalQueryReader {
  Future<ProfileUpdateProposalView> get(ProfileUpdateProposalQuery query);
  Future<ProfileUpdateProposalSlice> list(ProfileUpdateProposalListQuery query);
}

CloudOperationRequestPayload encodeCreateProfileUpdateProposalCommand(
  CreateProfileUpdateProposalCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'personaId': command.personaId},
  body: <String, Object?>{
    'proposalId': command.proposalId,
    'source': command.source.name,
    ...command.changes.toWire(),
  },
);

CloudOperationRequestPayload encodeConfirmProfileUpdateProposalCommand(
  ConfirmProfileUpdateProposalCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'id': command.proposalId},
  body: <String, Object?>{
    'expectedProposalVersion': command.expectedProposalVersion,
  },
);

CloudOperationRequestPayload encodeApplyProfileUpdateProposalCommand(
  ApplyProfileUpdateProposalCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'id': command.proposalId},
  body: <String, Object?>{
    'expectedProposalVersion': command.expectedProposalVersion,
  },
);

CloudOperationRequestPayload encodeRejectProfileUpdateProposalCommand(
  RejectProfileUpdateProposalCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'id': command.proposalId},
  body: <String, Object?>{
    'expectedProposalVersion': command.expectedProposalVersion,
  },
);

CloudOperationRequestPayload encodeProfileUpdateProposalQuery(
  ProfileUpdateProposalQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'id': query.proposalId},
);

CloudOperationRequestPayload encodeProfileUpdateProposalListQuery(
  ProfileUpdateProposalListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'personaId': query.personaId},
  queryParameters: <String, String>{
    if (query.cursor != null) 'cursor': query.cursor!,
    'limit': query.limit.toString(),
  },
);

ProfileUpdateProposalCommandResult decodeProfileUpdateProposalCommandResult(
  Object? value,
) {
  final map = _object(value, 'ProfileUpdateProposalCommandResult');
  _only(map, const <String>{'proposalId', 'version', 'status', 'replayed'});
  return ProfileUpdateProposalCommandResult(
    proposalId: _string(map, 'proposalId'),
    version: _positiveInt(map, 'version'),
    status: _status(map['status']),
    replayed: _bool(map, 'replayed'),
  );
}

ProfileUpdateProposalView decodeProfileUpdateProposalView(Object? value) =>
    _view(value);

ProfileUpdateProposalSlice decodeProfileUpdateProposalSlice(Object? value) {
  final map = _object(value, 'ProfileUpdateProposalSlice');
  _only(map, const <String>{'items', 'nextCursor'});
  final items = map['items'];
  if (items is! List<Object?>) {
    throw const FormatException(
      'ProfileUpdateProposalSlice.items must be a list',
    );
  }
  return ProfileUpdateProposalSlice(
    items: items.map(_view).toList(growable: false),
    nextCursor: _optionalString(map['nextCursor']),
  );
}

ProfileUpdateProposalView _view(Object? value) {
  final map = _object(value, 'ProfileUpdateProposalView');
  _only(map, const <String>{
    'id',
    'personaId',
    'source',
    'status',
    'displayName',
    'bio',
    'avatarMediaAssetId',
    'backgroundMediaAssetId',
    'isPrivate',
    'isolationLevel',
    'purposeHint',
    'reviewedBy',
    'targetPersonaExpectedVersion',
    'version',
    'createdAt',
    'updatedAt',
    'resolvedAt',
  });
  late final ProfileChangeSet changes;
  try {
    changes = ProfileChangeSet(
      displayName: _optionalString(map['displayName']),
      bio: _nullableString(map, 'bio'),
      avatarMediaAssetId: _optionalString(map['avatarMediaAssetId']),
      backgroundMediaAssetId: _optionalString(map['backgroundMediaAssetId']),
      isPrivate: _nullableBool(map, 'isPrivate'),
      isolationLevel: _optionalString(map['isolationLevel']),
      purposeHint: _optionalString(map['purposeHint']),
    );
  } on ArgumentError catch (error) {
    throw FormatException('invalid profile change set: ${error.message}');
  }
  return ProfileUpdateProposalView(
    id: _string(map, 'id'),
    personaId: _string(map, 'personaId'),
    source: _source(map['source']),
    status: _status(map['status']),
    changes: changes,
    reviewedBy: _optionalString(map['reviewedBy']),
    targetPersonaExpectedVersion: _optionalPositiveInt(
      map['targetPersonaExpectedVersion'],
    ),
    version: _positiveInt(map, 'version'),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
    resolvedAt: _optionalDate(map['resolvedAt']),
  );
}

Map<String, Object?> _object(Object? value, String name) {
  if (value is! Map) throw FormatException('$name must be an object');
  if (value.keys.any((key) => key is! String)) {
    throw FormatException('$name keys must be strings');
  }
  return value.cast<String, Object?>();
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  final unknown = map.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) {
    throw FormatException('unknown fields: ${unknown.join(',')}');
  }
}

String _string(Map<String, Object?> map, String key) {
  final value = _optionalString(map[key]);
  if (value == null) throw FormatException('$key must be a non-empty string');
  return value;
}

String? _nullableString(Map<String, Object?> map, String key) {
  if (!map.containsKey(key) || map[key] == null) return null;
  if (map[key] is! String) throw FormatException('$key must be a string');
  return (map[key] as String).trim();
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0) {
    throw FormatException('$key must be a positive integer');
  }
  return value;
}

int? _optionalPositiveInt(Object? value) {
  if (value == null) return null;
  if (value is! int || value <= 0) {
    throw const FormatException('optional version must be a positive integer');
  }
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

bool? _nullableBool(Map<String, Object?> map, String key) {
  if (!map.containsKey(key) || map[key] == null) return null;
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

DateTime _date(Map<String, Object?> map, String key) {
  final parsed = DateTime.tryParse(_string(map, key));
  if (parsed == null) throw FormatException('$key must be RFC3339');
  return parsed.toUtc();
}

DateTime? _optionalDate(Object? value) {
  if (value == null) return null;
  if (value is! String) {
    throw const FormatException('optional timestamp must be RFC3339');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw const FormatException('optional timestamp must be RFC3339');
  }
  return parsed.toUtc();
}

ProfileUpdateProposalSource _source(Object? value) =>
    ProfileUpdateProposalSource.values.firstWhere(
      (item) => item.name == value,
      orElse: () => throw FormatException('unknown proposal source $value'),
    );

ProfileUpdateProposalStatus _status(Object? value) =>
    ProfileUpdateProposalStatus.values.firstWhere(
      (item) => item.name == value,
      orElse: () => throw FormatException('unknown proposal status $value'),
    );

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

String? _optionalPreservingEmpty(String? value) =>
    value == null ? null : value.trim();

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) {
    throw const FormatException('optional string must be non-empty');
  }
  return value.trim();
}

void _positive(int value, String name) {
  if (value <= 0) throw ArgumentError.value(value, name, 'must be positive');
}
