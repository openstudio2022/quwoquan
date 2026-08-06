import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

enum IncomingCallPushAction {
  ring('ring'),
  cancel('cancel');

  const IncomingCallPushAction(this.wireName);

  final String wireName;

  static IncomingCallPushAction parse(Object? raw) {
    final normalized = raw is String ? raw.trim() : '';
    for (final value in values) {
      if (value.wireName == normalized) {
        return value;
      }
    }
    throw const FormatException('IncomingCallPushAction is invalid');
  }
}

@immutable
final class IncomingCallPushEnvelope {
  IncomingCallPushEnvelope({
    required this.action,
    required this.call,
    required DateTime occurredAt,
  }) : occurredAt = occurredAt.toUtc() {
    if (this.occurredAt.isAfter(call.expiresAt)) {
      throw const FormatException(
        'IncomingCallPushEnvelope.occurredAt exceeds expiresAt',
      );
    }
  }

  factory IncomingCallPushEnvelope.fromMap(Map<Object?, Object?> raw) {
    final occurredAt = DateTime.tryParse(
      raw['occurredAt'] is String ? raw['occurredAt']! as String : '',
    )?.toUtc();
    if (occurredAt == null) {
      throw const FormatException(
        'IncomingCallPushEnvelope.occurredAt is invalid',
      );
    }
    return IncomingCallPushEnvelope(
      action: IncomingCallPushAction.parse(raw['action']),
      call: IncomingCallEnvelope.fromMap(raw),
      occurredAt: occurredAt,
    );
  }

  final IncomingCallPushAction action;
  final IncomingCallEnvelope call;
  final DateTime occurredAt;
}

/// Realtime 与原生 Push 共用的来电信封。
///
/// 该类型只表达来电展示所需的最小可信字段；CallKit 继续直接使用 [callId]，
/// 禁止派生第二个 native call id。
@immutable
final class IncomingCallEnvelope {
  IncomingCallEnvelope({
    required String callId,
    required String deliveryKey,
    required String targetPersonaId,
    required String callType,
    required String callerName,
    required String sourceLabel,
    required String trustRelation,
    required DateTime expiresAt,
    String? callerPersonaId,
  }) : callId = _requiredUuid(callId),
       deliveryKey = _requiredString(
         deliveryKey,
         field: 'deliveryKey',
         maxLength: 256,
       ),
       targetPersonaId = _requiredString(
         targetPersonaId,
         field: 'targetPersonaId',
         maxLength: 128,
       ),
       callType = _requiredCallType(callType),
       callerName = _requiredString(
         callerName,
         field: 'callerName',
         maxLength: 160,
       ),
       sourceLabel = _requiredString(
         sourceLabel,
         field: 'sourceLabel',
         maxLength: 160,
       ),
       trustRelation = _requiredTrustRelation(trustRelation),
       expiresAt = expiresAt.toUtc(),
       callerPersonaId = _optionalString(callerPersonaId, maxLength: 128);

  factory IncomingCallEnvelope.fromMap(Map<Object?, Object?> raw) {
    final expiresAtRaw = _stringValue(raw['expiresAt']);
    final expiresAt = DateTime.tryParse(expiresAtRaw)?.toUtc();
    if (expiresAt == null) {
      throw const FormatException('IncomingCallEnvelope.expiresAt is invalid');
    }
    return IncomingCallEnvelope(
      callId: _stringValue(raw['callId']),
      deliveryKey: _stringValue(raw['deliveryKey']),
      targetPersonaId: _stringValue(raw['targetPersonaId']),
      callType: _stringValue(raw['callType']),
      callerName: _stringValue(raw['callerName']),
      sourceLabel: _stringValue(raw['sourceLabel']),
      trustRelation: _stringValue(raw['trustRelation']),
      expiresAt: expiresAt,
      callerPersonaId: _stringValueOrNull(raw['callerPersonaId']),
    );
  }

  final String callId;
  final String deliveryKey;
  final String targetPersonaId;
  final String callType;
  final String callerName;
  final String sourceLabel;
  final String trustRelation;
  final DateTime expiresAt;

  /// Realtime 外层 actor 可提供该字段；原生最小 Push 不依赖它才能先展示 CallKit。
  final String? callerPersonaId;

  bool get isVideo => callType == 'video';

  bool isExpiredAt(DateTime now) => !expiresAt.isAfter(now.toUtc());

  Map<String, Object> toMap() => <String, Object>{
    'callId': callId,
    'deliveryKey': deliveryKey,
    'targetPersonaId': targetPersonaId,
    'callType': callType,
    'callerName': callerName,
    'sourceLabel': sourceLabel,
    'trustRelation': trustRelation,
    'expiresAt': expiresAt.toIso8601String(),
    'callerPersonaId': ?callerPersonaId,
  };

  @override
  bool operator ==(Object other) {
    return other is IncomingCallEnvelope &&
        other.callId == callId &&
        other.deliveryKey == deliveryKey &&
        other.targetPersonaId == targetPersonaId &&
        other.callType == callType &&
        other.callerName == callerName &&
        other.sourceLabel == sourceLabel &&
        other.trustRelation == trustRelation &&
        other.expiresAt == expiresAt &&
        other.callerPersonaId == callerPersonaId;
  }

  @override
  int get hashCode => Object.hash(
    callId,
    deliveryKey,
    targetPersonaId,
    callType,
    callerName,
    sourceLabel,
    trustRelation,
    expiresAt,
    callerPersonaId,
  );

  static String _requiredUuid(String value) {
    final normalized = value.trim().toLowerCase();
    if (!Uuid.isValidUUID(fromString: normalized)) {
      throw const FormatException(
        'IncomingCallEnvelope.callId must be an RFC UUID',
      );
    }
    return normalized;
  }

  static String _requiredCallType(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized != 'audio' && normalized != 'video') {
      throw const FormatException(
        'IncomingCallEnvelope.callType must be audio or video',
      );
    }
    return normalized;
  }

  static String _requiredTrustRelation(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized != 'known' && normalized != 'possibly_unknown') {
      throw const FormatException(
        'IncomingCallEnvelope.trustRelation is invalid',
      );
    }
    return normalized;
  }

  static String _requiredString(
    String value, {
    required String field,
    required int maxLength,
  }) {
    final normalized = value.trim();
    if (normalized.isEmpty || normalized.length > maxLength) {
      throw FormatException('IncomingCallEnvelope.$field is invalid');
    }
    return normalized;
  }

  static String? _optionalString(String? value, {required int maxLength}) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) {
      return null;
    }
    if (normalized.length > maxLength) {
      throw const FormatException(
        'IncomingCallEnvelope optional field is too long',
      );
    }
    return normalized;
  }

  static String _stringValue(Object? value) => value is String ? value : '';

  static String? _stringValueOrNull(Object? value) {
    final normalized = _stringValue(value).trim();
    return normalized.isEmpty ? null : normalized;
  }
}

enum IncomingCallClaimResult { accepted, duplicate, expired }

/// 有界进程内去重器：WS 与 native Push 竞争时只允许一个展示面胜出。
final class BoundedIncomingCallDedupe {
  BoundedIncomingCallDedupe({this.capacity = 128})
    : assert(capacity > 0, 'capacity must be positive');

  final int capacity;
  final LinkedHashMap<String, DateTime> _deliveryKeys =
      LinkedHashMap<String, DateTime>();
  final LinkedHashMap<String, DateTime> _callIds =
      LinkedHashMap<String, DateTime>();

  IncomingCallClaimResult claim(
    IncomingCallEnvelope envelope, {
    DateTime? now,
  }) {
    final effectiveNow = (now ?? DateTime.now()).toUtc();
    _purgeExpired(effectiveNow);
    if (envelope.isExpiredAt(effectiveNow)) {
      return IncomingCallClaimResult.expired;
    }
    if (_deliveryKeys.containsKey(envelope.deliveryKey) ||
        _callIds.containsKey(envelope.callId)) {
      return IncomingCallClaimResult.duplicate;
    }
    _deliveryKeys[envelope.deliveryKey] = envelope.expiresAt;
    _callIds[envelope.callId] = envelope.expiresAt;
    _trim(_deliveryKeys);
    _trim(_callIds);
    return IncomingCallClaimResult.accepted;
  }

  void clear() {
    _deliveryKeys.clear();
    _callIds.clear();
  }

  void suppress(IncomingCallEnvelope envelope) {
    final expiresAt = envelope.expiresAt.toUtc();
    _deliveryKeys[envelope.deliveryKey] = expiresAt;
    _callIds[envelope.callId] = expiresAt;
    _trim(_deliveryKeys);
    _trim(_callIds);
  }

  void suppressCallId(String callId, {DateTime? until}) {
    final normalized = callId.trim().toLowerCase();
    if (!Uuid.isValidUUID(fromString: normalized)) {
      return;
    }
    _callIds[normalized] =
        (until ?? DateTime.now().toUtc().add(const Duration(minutes: 2)))
            .toUtc();
    _trim(_callIds);
  }

  void _purgeExpired(DateTime now) {
    _deliveryKeys.removeWhere((_, expiresAt) => !expiresAt.isAfter(now));
    _callIds.removeWhere((_, expiresAt) => !expiresAt.isAfter(now));
  }

  void _trim(LinkedHashMap<String, DateTime> entries) {
    while (entries.length > capacity) {
      entries.remove(entries.keys.first);
    }
  }
}
