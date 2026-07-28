import '../operation_request_payload.dart';
import 'account_session_contracts.dart';

/// CredentialBinding 聚合查询/命令的 pure contracts。
/// 真相源：quwoquan_service/services/user-service/contracts/account/credential_binding/{service,fields}.yaml。
/// 唯一性由 DB 约束保证；冲突映射 USER.AUTH.credential_conflict，
/// 解绑最后一个凭证映射 USER.AUTH.last_credential。

/// Alpha/test 对齐 USER.USER.not_found 的强类型边界信号。
///
/// production Remote 由 runtime mapper 抛出携带 RuntimeFailure 的 CloudException。
final class CredentialBindingNotFoundException implements Exception {
  const CredentialBindingNotFoundException();
}

/// Alpha/test 对齐 USER.AUTH.last_credential 的强类型边界信号。
final class LastCredentialUnbindException implements Exception {
  const LastCredentialUnbindException();
}

final class BindPhoneCredentialCommand {
  BindPhoneCredentialCommand({
    required String phone,
    required String otpCode,
    this.displayLabel,
  }) : phone = _required(phone, 'phone'),
       otpCode = _required(otpCode, 'otpCode');

  final String phone;
  final String otpCode;
  final String? displayLabel;
}

final class BindCarrierPhoneCredentialCommand {
  BindCarrierPhoneCredentialCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    this.displayLabel,
  }) : vendor = _required(vendor, 'vendor'),
       carrierToken = _required(carrierToken, 'carrierToken'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform');

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? displayLabel;
}

final class CompleteFederatedPhoneBindingCommand {
  CompleteFederatedPhoneBindingCommand({
    required String bindingTicket,
    required String phone,
    required String otpCode,
    required String challengeId,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : bindingTicket = _required(bindingTicket, 'bindingTicket'),
       phone = _required(phone, 'phone'),
       otpCode = _required(otpCode, 'otpCode'),
       challengeId = _required(challengeId, 'challengeId'),
       deviceId = _required(deviceId, 'deviceId'),
       platform = _required(platform, 'platform'),
       appVersion = _required(appVersion, 'appVersion'),
       agreementVersion = _required(agreementVersion, 'agreementVersion'),
       privacyVersion = _required(privacyVersion, 'privacyVersion');

  final String bindingTicket;
  final String phone;
  final String otpCode;
  final String challengeId;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;
}

final class UnbindCredentialCommand {
  UnbindCredentialCommand({required String credentialType})
    : credentialType = _required(credentialType, 'credentialType');

  final String credentialType;
}

final class ListCredentialsQuery {
  const ListCredentialsQuery();
}

/// 当前账号可见的脱敏凭证行；不包含 SECRET credentialKey。
final class CredentialBindingView {
  const CredentialBindingView({
    required this.id,
    required this.credentialType,
    required this.isActive,
    required this.boundAt,
    required this.version,
    this.displayLabel,
  });

  final String id;
  final String credentialType;
  final String? displayLabel;
  final bool isActive;
  final DateTime boundAt;
  final int version;
}

final class ListCredentialsSlice {
  ListCredentialsSlice({required Iterable<CredentialBindingView> items})
    : items = List<CredentialBindingView>.unmodifiable(items);

  final List<CredentialBindingView> items;
}

/// 凭证绑定/解绑命令的稳定提交回执。
final class CredentialBindingCommandResult {
  const CredentialBindingCommandResult({
    required this.credentialType,
    required this.isActive,
    required this.version,
    required this.idempotentReplay,
    this.displayLabel,
  });

  final String credentialType;
  final bool isActive;
  final int version;
  final bool idempotentReplay;
  final String? displayLabel;
}

abstract interface class CredentialBindingQuery {
  Future<ListCredentialsSlice> listCredentials(ListCredentialsQuery query);
}

/// 当前 App 商用 surface 暴露的凭据绑定写面。
///
/// metadata 中的通用 BindCredential 只服务非 App 管理能力，不进入本 Facet。
abstract interface class CredentialBindingCommandWriter {
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  );

  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  );

  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  );

  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  );
}

/// 兼容现有 composition root 的语义别名；不额外暴露通用 bind。
abstract interface class AppCredentialBindingCommandWriter
    implements CredentialBindingCommandWriter {}

CloudOperationRequestPayload encodeListCredentialsQuery(
  ListCredentialsQuery query,
) => const CloudOperationRequestPayload(body: null);

CloudOperationRequestPayload encodeBindPhoneCredentialCommand(
  BindPhoneCredentialCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'phone': command.phone,
    'otpCode': command.otpCode,
    if (command.displayLabel != null) 'displayLabel': command.displayLabel,
  },
);

CloudOperationRequestPayload encodeCompleteFederatedPhoneBindingCommand(
  CompleteFederatedPhoneBindingCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'bindingTicket': command.bindingTicket,
    'phone': command.phone,
    'otpCode': command.otpCode,
    'challengeId': command.challengeId,
    'deviceId': command.deviceId,
    'platform': command.platform,
    'appVersion': command.appVersion,
    'agreementVersion': command.agreementVersion,
    'privacyVersion': command.privacyVersion,
  },
);

CloudOperationRequestPayload encodeBindCarrierPhoneCredentialCommand(
  BindCarrierPhoneCredentialCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'vendor': command.vendor,
    'carrierToken': command.carrierToken,
    'deviceId': command.deviceId,
    'platform': command.platform,
    if (command.displayLabel != null) 'displayLabel': command.displayLabel,
  },
);

CloudOperationRequestPayload encodeUnbindCredentialCommand(
  UnbindCredentialCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'credentialType': command.credentialType},
);

ListCredentialsSlice decodeListCredentialsSlice(Object? value) {
  final map = _object(value, 'ListCredentialsSlice');
  _only(map, const <String>{'credentials'});
  final credentials = map['credentials'];
  if (credentials is! List) {
    throw const FormatException(
      'ListCredentialsSlice.credentials must be a list',
    );
  }
  return ListCredentialsSlice(
    items: credentials.map(decodeCredentialBindingView),
  );
}

CredentialBindingView decodeCredentialBindingView(Object? value) {
  final map = _object(value, 'CredentialBindingView');
  _only(map, const <String>{
    'id',
    'credentialType',
    'displayLabel',
    'isActive',
    'boundAt',
    'version',
  });
  return CredentialBindingView(
    id: _string(map, 'id'),
    credentialType: _string(map, 'credentialType'),
    displayLabel: _optionalString(map, 'displayLabel'),
    isActive: _bool(map, 'isActive'),
    boundAt: _dateTime(map, 'boundAt'),
    version: _positiveInt(map, 'version'),
  );
}

CredentialBindingCommandResult decodeCredentialBindingCommandResult(
  Object? value,
) {
  final map = _object(value, 'CredentialBindingCommandResult');
  _only(map, const <String>{
    'credentialType',
    'isActive',
    'version',
    'idempotentReplay',
    'displayLabel',
  });
  return CredentialBindingCommandResult(
    credentialType: _string(map, 'credentialType'),
    isActive: _bool(map, 'isActive'),
    version: _positiveInt(map, 'version'),
    idempotentReplay: _bool(map, 'idempotentReplay'),
    displayLabel: _optionalString(map, 'displayLabel'),
  );
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$label keys must be strings');
    }
    result[key] = entry.value;
  }
  return result;
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('unexpected key: $key');
    }
  }
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$key must be a string or null');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
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
  if (value is! bool) {
    throw FormatException('$key must be a boolean');
  }
  return value;
}

DateTime _dateTime(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String) {
    throw FormatException('$key must be an ISO-8601 timestamp');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$key must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}
