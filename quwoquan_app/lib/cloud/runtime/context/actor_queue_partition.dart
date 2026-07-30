import 'dart:convert';

import 'package:crypto/crypto.dart';

/// 离线队列的主体隔离键。
///
/// 原始 account/persona/device 标识不进入 Hive box 名；稳定摘要同时写入 envelope，
/// 刷盘时必须与当前 partition 完全相等，避免切号后用新 token 重放旧主体事件。
final class ActorQueuePartition {
  ActorQueuePartition({
    required String environment,
    String accountId = '',
    String personaId = '',
    String deviceId = '',
  }) : _environment = environment.trim(),
       _accountId = accountId.trim(),
       _personaId = personaId.trim(),
       _deviceId = deviceId.trim();

  final String _environment;
  final String _accountId;
  final String _personaId;
  final String _deviceId;

  /// The authenticated actor dimensions that own this queue partition.
  ///
  /// They are never part of a queue name; the Remote adapter uses them only to
  /// disclose the same verified actor context with a request.
  String get accountId => _accountId;
  String get personaId => _personaId;
  String get deviceId => _deviceId;

  bool get canPersist =>
      _environment.isNotEmpty &&
      (_accountId.isNotEmpty || _personaId.isNotEmpty || _deviceId.isNotEmpty);

  String get key {
    final canonical = jsonEncode(<String, String>{
      'environment': _environment,
      'accountId': _accountId,
      'personaId': _personaId,
      'deviceId': _deviceId,
    });
    return sha256.convert(utf8.encode(canonical)).toString().substring(0, 24);
  }

  /// Stable queue identity: semantic queue name + actor partition digest.
  String boxName(String queueName) => '${queueName}_actor_$key';

  bool acceptsEnvelope(Object? envelopeKey) =>
      canPersist && envelopeKey is String && envelopeKey == key;
}
