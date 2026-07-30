import '../operation_request_payload.dart';
part '../generated/requests/user/profile_update_proposal_contracts.requests.g.dart';

enum ProfileUpdateProposalSource { persona, assistant, external }

enum ProfileUpdateProposalStatus {
  pending,
  confirmed,
  applying,
  applied,
  rollingBack,
  rolledBack,
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

  List<String> get changedFields {
    final fields = <String>[
      if (displayName != null) 'displayName',
      if (bio != null) 'bio',
      if (avatarMediaAssetId != null) 'avatarMediaAssetId',
      if (backgroundMediaAssetId != null) 'backgroundMediaAssetId',
      if (isPrivate != null) 'isPrivate',
      if (isolationLevel != null) 'isolationLevel',
      if (purposeHint != null) 'purposeHint',
    ]..sort();
    return fields;
  }

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
    required this.reason,
    required this.evidenceRefs,
    required this.impactScope,
    required this.createdBy,
    required this.status,
    required this.changes,
    required this.reviewedBy,
    required this.applyAuditId,
    required this.rollbackDeadline,
    required this.rollbackAuditId,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
    required this.resolvedAt,
  });

  final String id;
  final String personaId;
  final ProfileUpdateProposalSource source;
  final String reason;
  final List<String> evidenceRefs;
  final List<String> impactScope;
  final String createdBy;
  final ProfileUpdateProposalStatus status;
  final ProfileChangeSet changes;
  final String? reviewedBy;
  final String? applyAuditId;
  final DateTime? rollbackDeadline;
  final String? rollbackAuditId;
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
  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  );
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  );
}

abstract interface class ProfileUpdateProposalQueryReader {
  Future<ProfileUpdateProposalView> get(ProfileUpdateProposalQuery query);
  Future<ProfileUpdateProposalSlice> list(ProfileUpdateProposalListQuery query);
}

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
    'reason',
    'evidenceRefs',
    'impactScope',
    'createdBy',
    'status',
    'displayName',
    'bio',
    'avatarMediaAssetId',
    'backgroundMediaAssetId',
    'isPrivate',
    'isolationLevel',
    'purposeHint',
    'reviewedBy',
    'applyAuditId',
    'rollbackDeadline',
    'rollbackAuditId',
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
    reason: _string(map, 'reason'),
    evidenceRefs: _stringList(map, 'evidenceRefs'),
    impactScope: _stringList(map, 'impactScope'),
    createdBy: _string(map, 'createdBy'),
    status: _status(map['status']),
    changes: changes,
    reviewedBy: _optionalString(map['reviewedBy']),
    applyAuditId: _optionalString(map['applyAuditId']),
    rollbackDeadline: _optionalDate(map['rollbackDeadline']),
    rollbackAuditId: _optionalString(map['rollbackAuditId']),
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

List<String> _stringList(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! List<Object?>) {
    throw FormatException('$key must be a list');
  }
  return value
      .map((item) {
        if (item is! String || item.trim().isEmpty) {
          throw FormatException('$key items must be non-empty strings');
        }
        return item.trim();
      })
      .toList(growable: false);
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

ProfileUpdateProposalStatus _status(Object? value) => switch (value) {
  'pending' => ProfileUpdateProposalStatus.pending,
  'confirmed' => ProfileUpdateProposalStatus.confirmed,
  'applying' => ProfileUpdateProposalStatus.applying,
  'applied' => ProfileUpdateProposalStatus.applied,
  'rolling_back' => ProfileUpdateProposalStatus.rollingBack,
  'rolled_back' => ProfileUpdateProposalStatus.rolledBack,
  'rejected' => ProfileUpdateProposalStatus.rejected,
  'expired' => ProfileUpdateProposalStatus.expired,
  _ => throw FormatException('unknown proposal status $value'),
};

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
