import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';

Map<String, Map<String, Object?>> circleTable(
  RehearsalInvocation invocation,
  String name,
) => invocation.store.records.putIfAbsent(
  'circle.$name',
  () => <String, Map<String, Object?>>{},
);

Never circleFailure(String code) =>
    throw localDomainCloudException('CIRCLE.USER.$code');

String requiredCirclePath(RehearsalInvocation invocation, String name) {
  final value = invocation.path(name).trim();
  if (value.isEmpty) circleFailure('invalid_argument');
  return value;
}

String requiredCircleBody(RehearsalInvocation invocation, String name) {
  final value = '${invocation.body[name] ?? ''}'.trim();
  if (value.isEmpty) circleFailure('invalid_argument');
  return value;
}

int bodyInt(RehearsalInvocation invocation, String name, {int fallback = 0}) =>
    (invocation.body[name] as num?)?.toInt() ?? fallback;

int rowVersion(Map<String, Object?> row) =>
    (row['version'] as num?)?.toInt() ??
    (row['aggregateVersion'] as num?)?.toInt() ??
    0;

void requireVersion(
  Map<String, Object?> row,
  Object? expected,
  String conflictCode,
) {
  if (expected == null) return;
  final value = (expected as num?)?.toInt();
  if (value == null || value != rowVersion(row)) circleFailure(conflictCode);
}

Map<String, Object?> requireRow(
  Map<String, Map<String, Object?>> table,
  String id,
  String code,
) => table[id] ?? circleFailure(code);

String circleMembershipKey(String circleId, String personaId) =>
    '$circleId::$personaId';
String circleGroupMembershipKey(
  String circleId,
  String groupId,
  String personaId,
) => '$circleId::$groupId::$personaId';
String gatheringParticipationKey(String gatheringId, String personaId) =>
    '$gatheringId::$personaId';

bool isCircleManager(RehearsalInvocation invocation, String circleId) {
  final circle = circleTable(invocation, 'circles')[circleId];
  if (circle?['ownerId'] == invocation.actorId) return true;
  final membership = circleTable(
    invocation,
    'memberships',
  )[circleMembershipKey(circleId, invocation.actorId)];
  return membership?['state'] == 'active' &&
      const {'owner', 'admin'}.contains(membership?['role']);
}

void requireCircleMember(RehearsalInvocation invocation, String circleId) {
  if (isCircleManager(invocation, circleId)) return;
  final membership = circleTable(
    invocation,
    'memberships',
  )[circleMembershipKey(circleId, invocation.actorId)];
  if (membership?['state'] != 'active') circleFailure('not_member');
}

void requireCircleManager(RehearsalInvocation invocation, String circleId) {
  if (!isCircleManager(invocation, circleId))
    circleFailure('permission_denied');
}

bool isGroupManager(
  RehearsalInvocation invocation,
  String circleId,
  String groupId,
) {
  if (isCircleManager(invocation, circleId)) return true;
  final membership = circleTable(
    invocation,
    'group_memberships',
  )[circleGroupMembershipKey(circleId, groupId, invocation.actorId)];
  return membership?['state'] == 'active' &&
      const {'owner', 'manager'}.contains(membership?['role']);
}

void requireGroupManager(
  RehearsalInvocation invocation,
  String circleId,
  String groupId,
) {
  if (!isGroupManager(invocation, circleId, groupId)) {
    circleFailure('permission_denied');
  }
}

String nowWire(RehearsalInvocation invocation) =>
    invocation.now().toUtc().toIso8601String();

Map<String, Object?> pageRows(
  RehearsalInvocation invocation,
  Iterable<Map<String, Object?>> source, {
  String itemsKey = 'items',
  String cursorKey = 'cursor',
  int maximum = 100,
  bool hasMore = false,
}) {
  final limit = int.tryParse(invocation.query('limit')) ?? 20;
  if (limit < 1 || limit > maximum) circleFailure('invalid_argument');
  final signature = jsonEncode(<String, Object?>{
    'operation': invocation.operation.canonicalOperationId,
    'actor': invocation.actorId,
    'path': invocation.payload.pathParameters,
    'query': Map<String, String>.from(invocation.payload.queryParameters)
      ..remove('cursor'),
  });
  var offset = 0;
  final raw = invocation.query('cursor');
  if (raw.isNotEmpty) {
    try {
      final decoded = jsonDecode(
        utf8.decode(base64Url.decode(base64Url.normalize(raw))),
      );
      if (decoded is! Map ||
          decoded['signature'] != signature ||
          decoded['offset'] is! int) {
        circleFailure('invalid_argument');
      }
      offset = decoded['offset'] as int;
    } catch (_) {
      circleFailure('invalid_argument');
    }
  }
  final rows = source.toList(growable: false);
  if (offset < 0 || offset > rows.length) circleFailure('invalid_argument');
  final end = (offset + limit).clamp(0, rows.length);
  final next = end < rows.length
      ? base64Url
            .encode(
              utf8.encode(jsonEncode({'signature': signature, 'offset': end})),
            )
            .replaceAll('=', '')
      : null;
  return <String, Object?>{
    itemsKey: rows.sublist(offset, end).map(cloneRehearsalValue).toList(),
    if (next != null) cursorKey: next,
    if (hasMore) 'hasMore': next != null,
  };
}

Map<String, Object?> circleCommand(Map<String, Object?> row) => {
  'circleId': row['id'],
  'version': row['version'],
  'status': row['status'],
  'idempotentReplay': false,
};

Map<String, Object?> membershipCommand(Map<String, Object?> row) => {
  'membershipId': row['membershipId'],
  'version': row['version'],
  'state': row['state'],
  'role': row['role'],
  'idempotentReplay': false,
};

Map<String, Object?> groupCommand(Map<String, Object?> row) => {
  'groupId': row['groupId'],
  'version': row['version'],
  'status': row['status'],
  'idempotentReplay': false,
};

Map<String, Object?> groupMembershipCommand(Map<String, Object?> row) => {
  'membershipId': row['membershipId'],
  'version': row['version'],
  'role': row['role'],
  'state': row['state'],
  'idempotentReplay': false,
};
