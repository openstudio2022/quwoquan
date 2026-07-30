import '../operation_request_payload.dart';
import 'persona_relationship_contracts.dart';
part '../generated/requests/user/contact_discovery_contracts.requests.g.dart';

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

final class ContactDiscoveryMatchResult {
  const ContactDiscoveryMatchResult({
    required this.hashedPhone,
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    required this.avatarVersion,
    required this.relationshipCapability,
    this.avatarUrl,
    this.region,
  });

  final String hashedPhone;
  final String personaId;
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
    required this.matchedPersonaIds,
    required this.matchCount,
    required this.matches,
    this.expireAt,
    this.completedAt,
  });

  final String id;
  final String status;
  final List<String> matchedPersonaIds;
  final int matchCount;
  final List<ContactDiscoveryMatchResult> matches;
  final DateTime? expireAt;
  final DateTime? completedAt;
}

final class ContactDiscoveryDismissResult {
  const ContactDiscoveryDismissResult({required this.status});

  final String status;
}

ContactDiscoveryResult decodeContactDiscoveryResult(Object? response) {
  final root = _object(response, 'ContactDiscoveryResult');
  final rawIDs = root['matchedPersonaIds'];
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
                personaId: _requiredField(item, 'personaId'),
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
    matchedPersonaIds: matchedIDs,
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
