import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/chat/chat_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/entity/entity_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/rtc/rtc_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/notification/notification_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

class DomainErrorCode {
  const DomainErrorCode({
    required this.domain,
    required this.code,
    required this.defaultMessage,
    required this.httpStatus,
    required this.value,
  });

  final String domain;
  final String code;
  final String defaultMessage;
  final int httpStatus;
  final Object value;
}

class DomainErrorCodeRegistry {
  const DomainErrorCodeRegistry._();

  static DomainErrorCode? fromCode(String? rawCode) {
    final code = rawCode?.trim() ?? '';
    if (code.isEmpty) return null;
    if (code.startsWith('CONTENT.')) {
      final value = ContentErrorCode.fromCode(code);
      return value == ContentErrorCode.unknown
          ? null
          : _fromContent(value, code);
    }
    if (code.startsWith('USER.')) {
      final value = UserErrorCode.fromCode(code);
      return value == null ? null : _fromUser(value);
    }
    if (code.startsWith('CHAT.')) {
      final value = ChatErrorCode.fromCode(code);
      return value == ChatErrorCode.unknown ? null : _fromChat(value);
    }
    if (code.startsWith('RTC.')) {
      final value = RtcErrorCode.fromCode(code);
      return value == null ? null : _fromRtc(value);
    }
    if (code.startsWith('INTEGRATION.')) {
      final value = IntegrationLocationErrorCode.fromCode(code);
      return value == IntegrationLocationErrorCode.unknown
          ? null
          : _fromIntegrationLocation(value);
    }
    if (code.startsWith('ASSISTANT.')) {
      final value = AssistantErrorCode.fromCode(code);
      return value == AssistantErrorCode.unknown ? null : _fromAssistant(value);
    }
    if (code.startsWith('CIRCLE.')) {
      final value = CircleErrorCode.fromCode(code);
      if (value != CircleErrorCode.unknown) return _fromCircle(value);
      final membershipValue = CircleMembershipErrorCode.fromCode(code);
      return membershipValue == CircleMembershipErrorCode.unknown
          ? null
          : _fromCircleMembership(membershipValue);
    }
    if (code.startsWith('ENTITY.')) {
      final value = EntityErrorCode.fromCode(code);
      return value == EntityErrorCode.unknown ? null : _fromEntity(value);
    }
    if (code.startsWith('NOTIFICATION.')) {
      final value = NotificationErrorCode.fromCode(code);
      return value == NotificationErrorCode.unknown
          ? null
          : _fromNotification(value);
    }
    return null;
  }

  static DomainErrorCode _fromContent(
    ContentErrorCode value,
    String originalCode,
  ) {
    return DomainErrorCode(
      domain: 'content',
      code: originalCode,
      defaultMessage:
          ContentErrorMessages.zh[value] ?? ContentErrorCode.unknown.name,
      httpStatus: _statusFromRuntimeCode(originalCode),
      value: value,
    );
  }

  static DomainErrorCode _fromUser(UserErrorCode value) {
    return DomainErrorCode(
      domain: 'user',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromChat(ChatErrorCode value) {
    return DomainErrorCode(
      domain: 'chat',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromRtc(RtcErrorCode value) {
    return DomainErrorCode(
      domain: 'rtc',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromIntegrationLocation(
    IntegrationLocationErrorCode value,
  ) {
    return DomainErrorCode(
      domain: 'integration_location',
      code: value.code,
      defaultMessage: IntegrationLocationErrorMessages.zh[value] ?? '',
      httpStatus: _statusFromRuntimeCode(value.code),
      value: value,
    );
  }

  static DomainErrorCode _fromAssistant(AssistantErrorCode value) {
    return DomainErrorCode(
      domain: 'assistant',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromCircle(CircleErrorCode value) {
    return DomainErrorCode(
      domain: 'circle',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromCircleMembership(
    CircleMembershipErrorCode value,
  ) {
    return DomainErrorCode(
      domain: 'circle',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromEntity(EntityErrorCode value) {
    return DomainErrorCode(
      domain: 'entity',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static DomainErrorCode _fromNotification(NotificationErrorCode value) {
    return DomainErrorCode(
      domain: 'notification',
      code: value.code,
      defaultMessage: value.defaultMessage,
      httpStatus: value.httpStatus,
      value: value,
    );
  }

  static int _statusFromRuntimeCode(String code) {
    if (code.contains('.MIDDLEWARE.')) return 504;
    if (code.contains('.SYSTEM.')) return 500;
    if (code.endsWith('_not_found') || code.endsWith('.not_found')) return 404;
    if (code.contains('unauthorized')) return 401;
    if (code.contains('forbidden') || code.contains('permission')) return 403;
    if (code.contains('rate_limited')) return 429;
    if (code.contains('conflict') || code.contains('duplicate')) return 409;
    return 400;
  }
}
