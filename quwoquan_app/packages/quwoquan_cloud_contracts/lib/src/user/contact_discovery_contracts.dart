import '../operation_request_payload.dart';
import 'persona_relationship_contracts.dart';

abstract interface class ContactDiscoveryCommandWriter {
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  );

  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  );
}

abstract interface class ContactDiscoveryQuery {
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  );
}

final class InitiateContactDiscoveryCommand {
  InitiateContactDiscoveryCommand({required List<String> hashedPhones})
    : hashedPhones = List<String>.unmodifiable(
        hashedPhones
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty),
      ) {
    if (this.hashedPhones.isEmpty) {
      throw ArgumentError.value(
        hashedPhones,
        'hashedPhones',
        'must not be empty',
      );
    }
  }

  final List<String> hashedPhones;
}

final class GetLatestContactDiscoveryQuery {
  const GetLatestContactDiscoveryQuery();
}

final class DismissContactDiscoveryCommand {
  DismissContactDiscoveryCommand({required String discoveryId})
    : discoveryId = _required(discoveryId, 'discoveryId');

  final String discoveryId;
}

final class ContactDiscoveryMatchResult {
  const ContactDiscoveryMatchResult({
    required this.hashedPhone,
    required this.subAccountId,
    required this.userHandle,
    required this.displayName,
    required this.avatarVersion,
    required this.relationshipCapability,
    this.avatarUrl,
    this.region,
  });

  final String hashedPhone;
  final String subAccountId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? region;
  final RelationshipCapabilityResult relationshipCapability;
}

final class ContactDiscoveryResult {
  const ContactDiscoveryResult({
    required this.id,
    required this.status,
    required this.matchedSubAccountIds,
    required this.matchCount,
    required this.matches,
    this.expireAt,
    this.completedAt,
  });

  final String id;
  final String status;
  final List<String> matchedSubAccountIds;
  final int matchCount;
  final List<ContactDiscoveryMatchResult> matches;
  final DateTime? expireAt;
  final DateTime? completedAt;
}

final class ContactDiscoveryDismissResult {
  const ContactDiscoveryDismissResult({required this.status});

  final String status;
}

CloudOperationRequestPayload encodeInitiateContactDiscoveryCommand(
  InitiateContactDiscoveryCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{'hashedPhones': command.hashedPhones},
  );
}

CloudOperationRequestPayload encodeGetLatestContactDiscoveryQuery(
  GetLatestContactDiscoveryQuery query,
) => const CloudOperationRequestPayload();

CloudOperationRequestPayload encodeDismissContactDiscoveryCommand(
  DismissContactDiscoveryCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'id': command.discoveryId},
  );
}

ContactDiscoveryResult decodeContactDiscoveryResult(Object? response) {
  final root = _object(response, 'ContactDiscoveryResult');
  final rawIDs = root['matchedSubAccountIds'];
  final rawMatches = root['matches'];
  final matchedIDs = rawIDs is List<Object?>
      ? rawIDs
            .map((value) => _optionalString(value))
            .whereType<String>()
            .toList(growable: false)
      : const <String>[];
  final matches = rawMatches is List<Object?>
      ? rawMatches
            .map<ContactDiscoveryMatchResult>((raw) {
              final item = _object(raw, 'ContactDiscoveryMatchResult');
              final capability = item['relationshipCapability'];
              return ContactDiscoveryMatchResult(
                hashedPhone: _requiredField(item, 'hashedPhone'),
                subAccountId: _requiredField(item, 'subAccountId'),
                userHandle: _requiredField(item, 'userHandle'),
                displayName: _requiredField(item, 'displayName'),
                avatarUrl: _optionalString(item['avatarUrl']),
                avatarVersion: _integer(item['avatarVersion']),
                region: _optionalString(item['region']),
                relationshipCapability: decodeRelationshipCapabilityResult(
                  capability,
                ),
              );
            })
            .toList(growable: false)
      : const <ContactDiscoveryMatchResult>[];
  return ContactDiscoveryResult(
    id: _requiredField(root, 'id'),
    status: _requiredField(root, 'status'),
    matchedSubAccountIds: matchedIDs,
    matchCount: _integer(root['matchCount'], fallback: matches.length),
    matches: matches,
    expireAt: _optionalTimestamp(root['expireAt']),
    completedAt: _optionalTimestamp(root['completedAt']),
  );
}

ContactDiscoveryDismissResult decodeContactDiscoveryDismissResult(
  Object? response,
) {
  final root = _object(response, 'ContactDiscoveryDismissResult');
  return ContactDiscoveryDismissResult(status: _requiredField(root, 'status'));
}

Map<Object?, Object?> _object(Object? value, String name) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name must be a JSON object');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = _optionalString(root[key]);
  if (value == null) {
    throw FormatException('missing required field "$key"');
  }
  return value;
}

String? _optionalString(Object? value) {
  final text = value is String ? value.trim() : '';
  return text.isEmpty ? null : text;
}

int _integer(Object? value, {int fallback = 0}) {
  return value is num ? value.toInt() : fallback;
}

DateTime? _optionalTimestamp(Object? value) {
  final text = _optionalString(value);
  return text == null ? null : DateTime.parse(text).toUtc();
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}
