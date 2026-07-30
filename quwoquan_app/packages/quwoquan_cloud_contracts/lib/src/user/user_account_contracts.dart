import '../operation_request_payload.dart';
part '../generated/requests/user/user_account_contracts.requests.g.dart';



/// 账号注销命令结果；`accountState` 恒为 closed。
final class CloseAccountResult {
  const CloseAccountResult({
    required this.accountState,
    required this.closedAt,
    required this.idempotentReplay,
  });

  final String accountState;
  final String closedAt;
  final bool idempotentReplay;
}

/// UserAccount 生命周期终态命令的对象级写面（R02：单接口 ≤10 方法）。
abstract interface class AccountLifecycleCommandWriter {
  Future<CloseAccountResult> closeAccount(CloseAccountCommand command);
}



CloseAccountResult decodeCloseAccountResult(Object? value) {
  final map = _object(value, 'CloseAccountResult');
  return CloseAccountResult(
    accountState: _requiredString(map, 'accountState'),
    closedAt: _requiredString(map, 'closedAt'),
    idempotentReplay: _requiredBool(map, 'idempotentReplay'),
  );
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _requiredString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is String && value.trim().isNotEmpty) return value.trim();
  throw FormatException('CloseAccountResult.$key must be a non-empty string');
}

bool _requiredBool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is bool) return value;
  throw FormatException('CloseAccountResult.$key must be a bool');
}
